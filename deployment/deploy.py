#!/usr/bin/env python3
"""
deploy.py
=========
Single-script infrastructure automation for the Movie Ticket Booking app.

Provisions, in order:
  1. DynamoDB tables: Tickets, Movies, Shows (PAY_PER_REQUEST, no capacity planning needed)
  2. Seeds the Movies/Shows tables with a BookMyShow-style demo catalogue
  3. S3 bucket for the static frontend, configured for public static website hosting
  4. EC2 instance (Amazon Linux 2023) running the Flask API via a user-data
     bootstrap script (installs Python, clones/uploads app code, runs gunicorn
     behind a systemd service on port 5000), inside a security group that
     allows :80/:443/:5000/:22
  5. API Gateway HTTP API with an ANY {proxy+} route forwarding to the EC2
     instance's public IP, so the frontend talks to a stable API Gateway URL
     instead of a raw EC2 IP.

Usage:
    python3 deploy.py up              # create everything
    python3 deploy.py status          # show current resource status / endpoints
    python3 deploy.py down            # tear everything down (asks to confirm)

Requires AWS credentials with permission to manage DynamoDB, S3, EC2, IAM
(instance profile), and API Gateway. Configure via standard boto3 credential
chain (env vars, ~/.aws/credentials, or an attached IAM role).
"""
import argparse
import base64
import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = "ap-south-1"  # Mumbai — change as needed
PROJECT = "movie-booking"
TICKETS_TABLE = "Tickets"
MOVIES_TABLE = "Movies"
SHOWS_TABLE = "Shows"
BUCKET_NAME_PREFIX = "movie-booking-frontend"
EC2_KEY_NAME = f"{PROJECT}-key"
SG_NAME = f"{PROJECT}-sg"
INSTANCE_TAG = f"{PROJECT}-api-server"
API_GATEWAY_NAME = f"{PROJECT}-api"
INSTANCE_TYPE = "t3.micro"  # Free-tier friendly

session = boto3.Session(region_name=REGION)
ddb = session.resource("dynamodb")
ddb_client = session.client("dynamodb")
ec2 = session.resource("ec2")
ec2_client = session.client("ec2")
s3 = session.client("s3")
apigw = session.client("apigatewayv2")
sts = session.client("sts")


def log(msg):
    print(f"[deploy] {msg}")


# ---------------------------------------------------------------------------
# 1. DynamoDB
# ---------------------------------------------------------------------------
def create_dynamodb_tables():
    tables = {
        TICKETS_TABLE: {
            "KeySchema": [
                {"AttributeName": "show_id", "KeyType": "HASH"},
                {"AttributeName": "seat_id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "show_id", "AttributeType": "S"},
                {"AttributeName": "seat_id", "AttributeType": "S"},
            ],
        },
        MOVIES_TABLE: {
            "KeySchema": [{"AttributeName": "movie_id", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "movie_id", "AttributeType": "S"}],
        },
        SHOWS_TABLE: {
            "KeySchema": [
                {"AttributeName": "movie_id", "KeyType": "HASH"},
                {"AttributeName": "show_id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "movie_id", "AttributeType": "S"},
                {"AttributeName": "show_id", "AttributeType": "S"},
            ],
        },
    }

    for name, schema in tables.items():
        try:
            ddb_client.describe_table(TableName=name)
            log(f"DynamoDB table '{name}' already exists, skipping.")
            continue
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        log(f"Creating DynamoDB table '{name}'...")
        ddb_client.create_table(
            TableName=name,
            KeySchema=schema["KeySchema"],
            AttributeDefinitions=schema["AttributeDefinitions"],
            BillingMode="PAY_PER_REQUEST",
        )
        waiter = ddb_client.get_waiter("table_exists")
        waiter.wait(TableName=name)
        log(f"Table '{name}' is ACTIVE.")


def seed_demo_catalogue():
    """Seed a small BookMyShow-style catalogue: movies + showtimes."""
    movies_table = ddb.Table(MOVIES_TABLE)
    shows_table = ddb.Table(SHOWS_TABLE)

    demo_movies = [
        {
            "movie_id": "mv001",
            "title": "Deep Drift",
            "genre": "Sci-Fi / Thriller",
            "language": "English",
            "duration_mins": 148,
            "rating": "UA",
            "imdb_rating": "8.8",
            "poster_url": "posters/tt1375666.svg",
            "description": "A skilled operative who steals secrets from deep within the subconscious is offered a chance at redemption: plant an idea instead of stealing one.",
        },
        {
            "movie_id": "mv002",
            "title": "Beyond the Stars",
            "genre": "Sci-Fi / Drama",
            "language": "English",
            "duration_mins": 169,
            "rating": "UA",
            "imdb_rating": "8.7",
            "poster_url": "posters/tt0816692.svg",
            "description": "A team of explorers travels through a wormhole in deep space in a desperate attempt to ensure humanity's survival.",
        },
        {
            "movie_id": "mv003",
            "title": "Chain Reaction",
            "genre": "Biography / Drama",
            "language": "English",
            "duration_mins": 180,
            "rating": "A",
            "imdb_rating": "8.4",
            "poster_url": "posters/tt15398776.svg",
            "description": "The story of a brilliant scientist and his role in a discovery that changes the world forever.",
        },
        {
            "movie_id": "mv004",
            "title": "Vendetta",
            "genre": "Action / Drama",
            "language": "Hindi",
            "duration_mins": 169,
            "rating": "UA",
            "imdb_rating": "7.0",
            "poster_url": "posters/tt11304740.svg",
            "description": "A man driven by a personal vendetta sets out to rectify the wrongs in society, fulfilling a promise made years ago.",
        },
        {
            "movie_id": "mv005",
            "title": "Multiverse Protocol",
            "genre": "Animation / Action",
            "language": "English",
            "duration_mins": 140,
            "rating": "U",
            "imdb_rating": "8.6",
            "poster_url": "posters/tt9362722.svg",
            "description": "A young hero catapults across the multiverse, encountering a team charged with protecting its very existence.",
        },
        {
            "movie_id": "mv006",
            "title": "The Hidden Nation",
            "genre": "Action / Adventure",
            "language": "English",
            "duration_mins": 161,
            "rating": "UA",
            "imdb_rating": "6.7",
            "poster_url": "posters/tt6443346.svg",
            "description": "The people of a hidden nation fight to protect their home from intervening world powers in a time of mourning.",
        },
    ]

    theatres = ["PVR Lower Parel", "INOX R-City Mall", "Cinepolis Andheri"]
    show_times = ["10:00", "13:30", "17:00", "19:30", "22:00"]
    show_dates = ["2026-07-01", "2026-07-02"]

    log("Seeding Movies table...")
    with movies_table.batch_writer() as batch:
        for m in demo_movies:
            batch.put_item(Item=m)

    log("Seeding Shows table (movies x theatres x dates x times)...")
    count = 0
    with shows_table.batch_writer() as batch:
        for m in demo_movies:
            for theatre in theatres:
                for date in show_dates:
                    for t in show_times:
                        show_id = f"{m['movie_id']}#{theatre.replace(' ', '-')}#{date}#{t}"
                        batch.put_item(Item={
                            "movie_id": m["movie_id"],
                            "show_id": show_id,
                            "theatre": theatre,
                            "show_date": date,
                            "show_time": t,
                        })
                        count += 1
    log(f"Seeded {len(demo_movies)} movies and {count} showtimes.")


# ---------------------------------------------------------------------------
# 2. S3 static frontend bucket
# ---------------------------------------------------------------------------
def create_s3_bucket():
    account_id = sts.get_caller_identity()["Account"]
    bucket_name = f"{BUCKET_NAME_PREFIX}-{account_id}"

    try:
        s3.head_bucket(Bucket=bucket_name)
        log(f"S3 bucket '{bucket_name}' already exists.")
    except ClientError:
        log(f"Creating S3 bucket '{bucket_name}'...")
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )

    # Allow public read for static website hosting
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": False,
            "IgnorePublicAcls": False,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": False,
        },
    )
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket_name}/*",
        }],
    }
    s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
    s3.put_bucket_website(
        Bucket=bucket_name,
        WebsiteConfiguration={
            "IndexDocument": {"Suffix": "index.html"},
            "ErrorDocument": {"Key": "index.html"},
        },
    )
    log(f"S3 static website hosting enabled on '{bucket_name}'.")
    return bucket_name


def upload_frontend(bucket_name, frontend_dir):
    import os
    import mimetypes

    log(f"Uploading frontend files from {frontend_dir} to s3://{bucket_name} ...")
    for root, _, files in os.walk(frontend_dir):
        for fname in files:
            local_path = os.path.join(root, fname)
            key = os.path.relpath(local_path, frontend_dir)
            content_type, _ = mimetypes.guess_type(local_path)
            extra = {"ContentType": content_type} if content_type else {}
            s3.upload_file(local_path, bucket_name, key, ExtraArgs=extra)
    log("Frontend upload complete.")


# ---------------------------------------------------------------------------
# 3. EC2 — security group, key pair, instance with bootstrap user-data
# ---------------------------------------------------------------------------
def ensure_security_group():
    vpc_id = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    existing = ec2_client.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [SG_NAME]}, {"Name": "vpc-id", "Values": [vpc_id]}]
    )["SecurityGroups"]
    if existing:
        log(f"Security group '{SG_NAME}' already exists.")
        return existing[0]["GroupId"]

    log(f"Creating security group '{SG_NAME}'...")
    sg = ec2_client.create_security_group(
        GroupName=SG_NAME, Description="Movie booking Flask API SG", VpcId=vpc_id
    )
    sg_id = sg["GroupId"]
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 5000, "ToPort": 5000, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ],
    )
    return sg_id


def ensure_key_pair():
    try:
        ec2_client.describe_key_pairs(KeyNames=[EC2_KEY_NAME])
        log(f"Key pair '{EC2_KEY_NAME}' already exists.")
    except ClientError:
        log(f"Creating key pair '{EC2_KEY_NAME}'...")
        resp = ec2_client.create_key_pair(KeyName=EC2_KEY_NAME)
        with open(f"{EC2_KEY_NAME}.pem", "w") as f:
            f.write(resp["KeyMaterial"])
        import os
        os.chmod(f"{EC2_KEY_NAME}.pem", 0o400)
        log(f"Saved private key to {EC2_KEY_NAME}.pem (chmod 400). Keep this safe!")


def get_user_data_script():
    """
    Bootstrap script run on first boot. Installs Python3/pip/git, fetches
    application code (placeholder fetch — in `deploy.py upload-code` we scp
    the real files), installs deps, and runs the app as a systemd service.
    """
    return """#!/bin/bash
set -e
dnf update -y
dnf install -y python3 python3-pip git
mkdir -p /opt/movie-booking
cat > /etc/systemd/system/movie-booking.service << 'EOF'
[Unit]
Description=Movie Booking Flask API
After=network.target

[Service]
WorkingDirectory=/opt/movie-booking
Environment="AWS_REGION=ap-south-1"
Environment="TICKETS_TABLE=Tickets"
Environment="MOVIES_TABLE=Movies"
Environment="SHOWS_TABLE=Shows"
ExecStart=/usr/bin/python3 -m gunicorn -w 3 -b 0.0.0.0:5000 wsgi:app
Restart=always
User=ec2-user

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
echo "Bootstrap complete. Upload app code to /opt/movie-booking then: systemctl enable --now movie-booking"
"""


def create_iam_instance_profile():
    """EC2 needs permission to read/write DynamoDB without embedding access keys."""
    iam = session.client("iam")
    role_name = f"{PROJECT}-ec2-role"
    profile_name = f"{PROJECT}-ec2-profile"

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }
    try:
        iam.get_role(RoleName=role_name)
        log(f"IAM role '{role_name}' already exists.")
    except ClientError:
        log(f"Creating IAM role '{role_name}'...")
        iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust_policy))
        iam.attach_role_policy(RoleName=role_name, PolicyArn="arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess")
        time.sleep(10)  # IAM propagation delay

    try:
        iam.get_instance_profile(InstanceProfileName=profile_name)
    except ClientError:
        iam.create_instance_profile(InstanceProfileName=profile_name)
        iam.add_role_to_instance_profile(InstanceProfileName=profile_name, RoleName=role_name)
        time.sleep(10)

    return profile_name


def get_latest_amazon_linux_ami():
    resp = ec2_client.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": ["al2023-ami-*-x86_64"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )
    images = sorted(resp["Images"], key=lambda x: x["CreationDate"], reverse=True)
    return images[0]["ImageId"]


def launch_ec2_instance():
    existing = list(ec2.instances.filter(
        Filters=[{"Name": "tag:Name", "Values": [INSTANCE_TAG]},
                 {"Name": "instance-state-name", "Values": ["pending", "running"]}]
    ))
    if existing:
        inst = existing[0]
        log(f"EC2 instance already running: {inst.id} ({inst.public_ip_address})")
        return inst

    sg_id = ensure_security_group()
    ensure_key_pair()
    profile_name = create_iam_instance_profile()
    ami_id = get_latest_amazon_linux_ami()

    log(f"Launching EC2 instance ({INSTANCE_TYPE}, AMI {ami_id})...")
    instances = ec2.create_instances(
        ImageId=ami_id,
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        KeyName=EC2_KEY_NAME,
        SecurityGroupIds=[sg_id],
        IamInstanceProfile={"Name": profile_name},
        UserData=get_user_data_script(),
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": INSTANCE_TAG}]}],
    )
    instance = instances[0]
    log("Waiting for instance to enter 'running' state...")
    instance.wait_until_running()
    instance.reload()
    log(f"EC2 instance running: {instance.id}  public IP: {instance.public_ip_address}")
    return instance


# ---------------------------------------------------------------------------
# 4. API Gateway (HTTP API) — proxy all requests to EC2
# ---------------------------------------------------------------------------
def create_api_gateway(ec2_public_ip):
    existing = apigw.get_apis()["Items"]
    api = next((a for a in existing if a["Name"] == API_GATEWAY_NAME), None)

    # Note: the integration URI must reference {proxy} (no '+') -- that's how
    # HTTP API path-parameter substitution works for proxy integrations.
    target_url = f"http://{ec2_public_ip}:5000/{{proxy}}"

    if api:
        log(f"API Gateway '{API_GATEWAY_NAME}' already exists: {api['ApiEndpoint']}")
        api_id = api["ApiId"]
        integrations = apigw.get_integrations(ApiId=api_id)["Items"]

        if integrations:
            integration_id = integrations[0]["IntegrationId"]
            apigw.update_integration(
                ApiId=api_id,
                IntegrationId=integration_id,
                IntegrationUri=target_url,
            )
            log("Updated integration target to current EC2 IP.")
        else:
            # Prior run likely failed before the integration was created.
            log("No integration found on existing API -- creating one now.")
            integration = apigw.create_integration(
                ApiId=api_id,
                IntegrationType="HTTP_PROXY",
                IntegrationMethod="ANY",
                IntegrationUri=target_url,
                PayloadFormatVersion="1.0",
            )
            integration_id = integration["IntegrationId"]

        existing_routes = {r["RouteKey"] for r in apigw.get_routes(ApiId=api_id)["Items"]}
        if "ANY /{proxy+}" not in existing_routes:
            apigw.create_route(ApiId=api_id, RouteKey="ANY /{proxy+}", Target=f"integrations/{integration_id}")
            log("Created missing route ANY /{proxy+}.")

        existing_stages = {s["StageName"] for s in apigw.get_stages(ApiId=api_id)["Items"]}
        if "$default" not in existing_stages:
            apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
            log("Created missing $default stage.")

        return api["ApiEndpoint"]

    log(f"Creating API Gateway HTTP API '{API_GATEWAY_NAME}'...")
    # Create the bare API first (no Target shorthand -- that quick-create path
    # only wires up a $default route with no path variables, which is
    # incompatible with a {proxy} integration URI and fails validation).
    api = apigw.create_api(Name=API_GATEWAY_NAME, ProtocolType="HTTP")
    api_id = api["ApiId"]

    integration = apigw.create_integration(
        ApiId=api_id,
        IntegrationType="HTTP_PROXY",
        IntegrationMethod="ANY",
        IntegrationUri=target_url,
        PayloadFormatVersion="1.0",
    )
    integration_id = integration["IntegrationId"]

    # ANY /{proxy+} forwards every path/method to EC2, with the matched
    # path captured in the `proxy` route/path parameter that the
    # integration URI above interpolates into. Every real endpoint in this
    # app lives under /api/... (at least one path segment), so {proxy+}
    # covers all of them. We deliberately do NOT add a separate "ANY /"
    # route: a route with no path variable cannot bind to an integration
    # URI that references {proxy} -- AWS rejects that combination outright.
    apigw.create_route(
        ApiId=api_id,
        RouteKey="ANY /{proxy+}",
        Target=f"integrations/{integration_id}",
    )

    apigw.create_stage(
        ApiId=api_id,
        StageName="$default",
        AutoDeploy=True,
    )

    api = apigw.get_api(ApiId=api_id)
    log(f"API Gateway created: {api['ApiEndpoint']}")
    return api["ApiEndpoint"]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def up(frontend_dir=None):
    log(f"Deploying '{PROJECT}' to region {REGION}...")
    create_dynamodb_tables()
    seed_demo_catalogue()
    bucket_name = create_s3_bucket()
    if frontend_dir:
        upload_frontend(bucket_name, frontend_dir)
    instance = launch_ec2_instance()
    log("Sleeping 30s to let the instance finish its boot bootstrap...")
    time.sleep(30)
    api_endpoint = create_api_gateway(instance.public_ip_address)

    s3_website_url = f"http://{bucket_name}.s3-website.{REGION}.amazonaws.com"
    print("\n" + "=" * 70)
    print("DEPLOYMENT SUMMARY")
    print("=" * 70)
    print(f"Frontend (S3 static site): {s3_website_url}")
    print(f"API Gateway endpoint:      {api_endpoint}")
    print(f"EC2 instance:              {instance.id}  ({instance.public_ip_address})")
    print(f"DynamoDB tables:           {TICKETS_TABLE}, {MOVIES_TABLE}, {SHOWS_TABLE}")
    print("=" * 70)
    print("\nNEXT STEP: upload backend code to the EC2 instance, then run:")
    print(f"  scp -i {EC2_KEY_NAME}.pem -r backend/* ec2-user@{instance.public_ip_address}:/opt/movie-booking/")
    print(f"  ssh -i {EC2_KEY_NAME}.pem ec2-user@{instance.public_ip_address} \\")
    print("    'cd /opt/movie-booking && sudo pip3 install -r requirements.txt && "
          "sudo systemctl enable --now movie-booking'")


def status():
    try:
        for t in [TICKETS_TABLE, MOVIES_TABLE, SHOWS_TABLE]:
            desc = ddb_client.describe_table(TableName=t)["Table"]
            print(f"DynamoDB[{t}]: {desc['TableStatus']}  ({desc['ItemCount']} items)")
    except ClientError as e:
        print("DynamoDB:", e)

    instances = list(ec2.instances.filter(
        Filters=[{"Name": "tag:Name", "Values": [INSTANCE_TAG]},
                 {"Name": "instance-state-name", "Values": ["running", "pending", "stopped"]}]
    ))
    for inst in instances:
        print(f"EC2: {inst.id}  state={inst.state['Name']}  ip={inst.public_ip_address}")

    apis = apigw.get_apis()["Items"]
    for a in apis:
        if a["Name"] == API_GATEWAY_NAME:
            print(f"API Gateway: {a['ApiEndpoint']}")


def down():
    confirm = input("This will DELETE all DynamoDB tables, the EC2 instance, S3 bucket, and API Gateway. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    for t in [TICKETS_TABLE, MOVIES_TABLE, SHOWS_TABLE]:
        try:
            ddb_client.delete_table(TableName=t)
            log(f"Deleted DynamoDB table {t}")
        except ClientError as e:
            log(f"Skip {t}: {e}")

    instances = list(ec2.instances.filter(
        Filters=[{"Name": "tag:Name", "Values": [INSTANCE_TAG]},
                 {"Name": "instance-state-name", "Values": ["running", "pending", "stopped"]}]
    ))
    for inst in instances:
        inst.terminate()
        log(f"Terminating EC2 instance {inst.id}")

    account_id = sts.get_caller_identity()["Account"]
    bucket_name = f"{BUCKET_NAME_PREFIX}-{account_id}"
    try:
        objs = s3.list_objects_v2(Bucket=bucket_name).get("Contents", [])
        if objs:
            s3.delete_objects(Bucket=bucket_name, Delete={"Objects": [{"Key": o["Key"]} for o in objs]})
        s3.delete_bucket(Bucket=bucket_name)
        log(f"Deleted S3 bucket {bucket_name}")
    except ClientError as e:
        log(f"Skip S3 bucket: {e}")

    apis = apigw.get_apis()["Items"]
    for a in apis:
        if a["Name"] == API_GATEWAY_NAME:
            apigw.delete_api(ApiId=a["ApiId"])
            log(f"Deleted API Gateway {a['ApiId']}")

    log("Teardown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy the movie booking app infra to AWS")
    parser.add_argument("action", choices=["up", "status", "down"])
    parser.add_argument("--frontend-dir", default="../frontend", help="Path to frontend static files for S3 upload")
    args = parser.parse_args()

    if args.action == "up":
        up(frontend_dir=args.frontend_dir)
    elif args.action == "status":
        status()
    elif args.action == "down":
        down()