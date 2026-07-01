"""Run the Flask app locally against a moto-mocked DynamoDB, with demo data seeded,
so we can visually test the frontend end-to-end before real AWS deployment."""
import os
os.environ["AWS_REGION"] = "ap-south-1"
os.environ["TICKETS_TABLE"] = "Tickets"
os.environ["MOVIES_TABLE"] = "Movies"
os.environ["SHOWS_TABLE"] = "Shows"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"

from moto import mock_aws

mocker = mock_aws()
mocker.start()

import boto3
ddb = boto3.client("dynamodb", region_name="ap-south-1")
ddb.create_table(
    TableName="Tickets",
    KeySchema=[{"AttributeName": "show_id", "KeyType": "HASH"},
               {"AttributeName": "seat_id", "KeyType": "RANGE"}],
    AttributeDefinitions=[{"AttributeName": "show_id", "AttributeType": "S"},
                           {"AttributeName": "seat_id", "AttributeType": "S"}],
    BillingMode="PAY_PER_REQUEST",
)
ddb.create_table(
    TableName="Movies",
    KeySchema=[{"AttributeName": "movie_id", "KeyType": "HASH"}],
    AttributeDefinitions=[{"AttributeName": "movie_id", "AttributeType": "S"}],
    BillingMode="PAY_PER_REQUEST",
)
ddb.create_table(
    TableName="Shows",
    KeySchema=[{"AttributeName": "movie_id", "KeyType": "HASH"},
               {"AttributeName": "show_id", "KeyType": "RANGE"}],
    AttributeDefinitions=[{"AttributeName": "movie_id", "AttributeType": "S"},
                           {"AttributeName": "show_id", "AttributeType": "S"}],
    BillingMode="PAY_PER_REQUEST",
)

# seed movies (reuse the same demo catalogue as deploy.py)
import sys
sys.path.insert(0, "../deployment")
import importlib.util
spec = importlib.util.spec_from_file_location("deploy", "../deployment/deploy.py")
deploy_mod = importlib.util.module_from_spec(spec)
# avoid executing argparse main block
import types
sys.modules["deploy"] = deploy_mod
# Patch the resource/client objects in deploy module to use our mocked session
spec.loader.exec_module(deploy_mod)
deploy_mod.seed_demo_catalogue()

from app import app
app.run(host="0.0.0.0", port=5000, debug=False)
