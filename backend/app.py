"""
Movie Ticket Booking Backend
=============================
Flask + boto3 + DynamoDB backend, designed to run on EC2 behind API Gateway.

APIs:
    POST   /api/book              -> book one or more seats for a show (atomic, no double-booking)
    GET    /api/tickets           -> get all tickets (optionally filter by ?movie_id= or ?show_id=)
    DELETE /api/tickets           -> delete all tickets (optionally scoped by ?show_id=)
    GET    /api/movies            -> list movies (seed/demo catalogue, served from DynamoDB)
    GET    /api/shows/<movie_id>  -> list showtimes for a movie
    GET    /api/seats/<show_id>   -> seat map + which seats are already booked
    DELETE /api/tickets/<ticket_id> -> cancel a single ticket

Data model (single-table DynamoDB):
    Tickets table
        PK: show_id   (string)  e.g. "tt0468569#PVR-LowerParel#2026-07-01#19:30"
        SK: seat_id   (string)  e.g. "G12"
        Attributes: ticket_id, movie_id, movie_title, theatre, show_date, show_time,
                    seat_id, seat_type, price, customer_name, customer_email, booked_at

    The composite key (show_id, seat_id) is the UNIQUE constraint. A conditional
    put_item with attribute_not_exists(seat_id) guarantees that two simultaneous
    requests for the same seat on the same show can NEVER both succeed -- DynamoDB
    resolves the race natively, no application-level locking needed.
"""
import os
import uuid
import datetime
import logging

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from flask import Flask, request, jsonify
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("movie-booking")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
TICKETS_TABLE_NAME = os.environ.get("TICKETS_TABLE", "Tickets")
MOVIES_TABLE_NAME = os.environ.get("MOVIES_TABLE", "Movies")
SHOWS_TABLE_NAME = os.environ.get("SHOWS_TABLE", "Shows")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
tickets_table = dynamodb.Table(TICKETS_TABLE_NAME)
movies_table = dynamodb.Table(MOVIES_TABLE_NAME)
shows_table = dynamodb.Table(SHOWS_TABLE_NAME)

app = Flask(__name__)
CORS(app)  # allow the S3-hosted frontend to call this API across origins


def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"


def error_response(message, status=400, **extra):
    body = {"success": False, "error": message}
    body.update(extra)
    return jsonify(body), status


# ---------------------------------------------------------------------------
# Health check (used by EC2 / load balancer / API Gateway integration tests)
# ---------------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"success": True, "status": "ok", "time": now_iso()})


# ---------------------------------------------------------------------------
# Movies & Shows (catalogue, BookMyShow-style browsing)
# ---------------------------------------------------------------------------
@app.route("/api/movies", methods=["GET"])
def get_movies():
    try:
        resp = movies_table.scan()
        movies = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = movies_table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            movies.extend(resp.get("Items", []))
        return jsonify({"success": True, "count": len(movies), "movies": movies})
    except ClientError as e:
        logger.exception("get_movies failed")
        return error_response(str(e), 500)


@app.route("/api/shows/<movie_id>", methods=["GET"])
def get_shows(movie_id):
    try:
        resp = shows_table.query(KeyConditionExpression=Key("movie_id").eq(movie_id))
        return jsonify({"success": True, "shows": resp.get("Items", [])})
    except ClientError as e:
        logger.exception("get_shows failed")
        return error_response(str(e), 500)


@app.route("/api/seats/<path:show_id>", methods=["GET"])
def get_seats(show_id):
    """Return the full seat map for a show plus which seats are taken."""
    try:
        resp = tickets_table.query(KeyConditionExpression=Key("show_id").eq(show_id))
        booked = [item["seat_id"] for item in resp.get("Items", [])]
        return jsonify({"success": True, "show_id": show_id, "booked_seats": booked})
    except ClientError as e:
        logger.exception("get_seats failed")
        return error_response(str(e), 500)


# ---------------------------------------------------------------------------
# Booking — the critical, duplicate-proof endpoint
# ---------------------------------------------------------------------------
@app.route("/api/book", methods=["POST"])
def book_ticket():
    """
    Book one or more seats atomically.

    Request JSON:
    {
        "show_id": "tt0468569#PVR-LowerParel#2026-07-01#19:30",
        "movie_id": "tt0468569",
        "movie_title": "Inception",
        "theatre": "PVR Lower Parel",
        "show_date": "2026-07-01",
        "show_time": "19:30",
        "seats": [{"seat_id": "G12", "seat_type": "Premium", "price": 350}, ...],
        "customer_name": "Heramb",
        "customer_email": "heramb@example.com"
    }

    Each seat is written with a conditional expression so it can only be
    booked if it doesn't already exist for that show_id. If ANY seat in the
    batch is already taken, the whole booking is rolled back (we use
    transact_write_items so it's all-or-nothing) and a 409 is returned
    listing which seats were already gone, so the frontend can re-render
    the seat map with fresh data.
    """
    data = request.get_json(silent=True) or {}

    required = ["show_id", "movie_id", "movie_title", "theatre", "show_date", "show_time", "seats"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return error_response(f"Missing required fields: {', '.join(missing)}")

    seats = data["seats"]
    if not isinstance(seats, list) or len(seats) == 0:
        return error_response("`seats` must be a non-empty list")
    if len(seats) > 10:
        return error_response("Cannot book more than 10 seats in a single transaction")

    seat_ids = [s.get("seat_id") for s in seats]
    if len(seat_ids) != len(set(seat_ids)):
        return error_response("Duplicate seat_id values within the same booking request")

    customer_name = data.get("customer_name", "Guest")
    customer_email = data.get("customer_email", "")
    show_id = data["show_id"]
    booking_id = str(uuid.uuid4())
    booked_at = now_iso()

    transact_items = []
    tickets_to_return = []

    for seat in seats:
        seat_id = seat.get("seat_id")
        if not seat_id:
            return error_response("Every seat must include a seat_id")

        ticket_id = str(uuid.uuid4())
        item = {
            "show_id": show_id,
            "seat_id": seat_id,
            "ticket_id": ticket_id,
            "booking_id": booking_id,
            "movie_id": data["movie_id"],
            "movie_title": data["movie_title"],
            "theatre": data["theatre"],
            "show_date": data["show_date"],
            "show_time": data["show_time"],
            "seat_type": seat.get("seat_type", "Standard"),
            "price": seat.get("price", 0),
            "customer_name": customer_name,
            "customer_email": customer_email,
            "booked_at": booked_at,
        }
        tickets_to_return.append(item)
        transact_items.append({
            "Put": {
                "TableName": TICKETS_TABLE_NAME,
                "Item": {k: _to_dynamo(v) for k, v in item.items()},
                # THE key line: this seat can only be written if it does not
                # already exist for this show -> guarantees no duplicate seats,
                # even under concurrent requests.
                "ConditionExpression": "attribute_not_exists(seat_id)",
            }
        })

    client = boto3.client("dynamodb", region_name=AWS_REGION)
    try:
        client.transact_write_items(TransactItems=transact_items)
    except client.exceptions.TransactionCanceledException as e:
        # Figure out which seats collided so the frontend can show a precise error
        reasons = e.response.get("CancellationReasons", [])
        conflicted = [
            seat_ids[i] for i, r in enumerate(reasons)
            if r.get("Code") == "ConditionalCheckFailed"
        ]
        logger.info("Booking conflict on show=%s seats=%s", show_id, conflicted)
        return error_response(
            "One or more selected seats were just booked by someone else.",
            status=409,
            conflicted_seats=conflicted,
        )
    except ClientError as e:
        logger.exception("book_ticket transaction failed")
        return error_response(str(e), 500)

    return jsonify({
        "success": True,
        "booking_id": booking_id,
        "tickets": tickets_to_return,
    }), 201


def _to_dynamo(value):
    """boto3 resource handles type conversion for us when going through
    Table, but transact_write_items via the low-level client needs typed
    values. Keep it simple: cast numbers, leave strings as-is."""
    import decimal
    if isinstance(value, float):
        return {"N": str(value)}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, int):
        return {"N": str(value)}
    if isinstance(value, decimal.Decimal):
        return {"N": str(value)}
    return {"S": str(value)}


# ---------------------------------------------------------------------------
# Get all tickets
# ---------------------------------------------------------------------------
@app.route("/api/tickets", methods=["GET"])
def get_tickets():
    """
    Get all tickets. Optional query params:
      ?show_id=...     scope to one show (efficient Query)
      ?movie_id=...    filter by movie (Scan + filter; fine at this scale)
      ?email=...       filter by customer email
    """
    show_id = request.args.get("show_id")
    movie_id = request.args.get("movie_id")
    email = request.args.get("email")

    try:
        if show_id:
            resp = tickets_table.query(KeyConditionExpression=Key("show_id").eq(show_id))
            items = resp.get("Items", [])
        else:
            resp = tickets_table.scan()
            items = resp.get("Items", [])
            while "LastEvaluatedKey" in resp:
                resp = tickets_table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
                items.extend(resp.get("Items", []))

            if movie_id:
                items = [i for i in items if i.get("movie_id") == movie_id]
            if email:
                items = [i for i in items if i.get("customer_email") == email]

        items.sort(key=lambda x: x.get("booked_at", ""), reverse=True)
        return jsonify({"success": True, "count": len(items), "tickets": items})
    except ClientError as e:
        logger.exception("get_tickets failed")
        return error_response(str(e), 500)


# ---------------------------------------------------------------------------
# Delete all tickets
# ---------------------------------------------------------------------------
@app.route("/api/tickets", methods=["DELETE"])
def delete_all_tickets():
    """
    Delete ALL tickets, or all tickets for a given ?show_id=.
    Batched with batch_writer for efficiency. Returns count deleted.
    Protected by a confirmation flag to avoid accidental wipes from the UI.
    """
    show_id = request.args.get("show_id")
    confirm = request.args.get("confirm") or (request.get_json(silent=True) or {}).get("confirm")
    if not confirm:
        return error_response(
            "Refusing to delete without confirmation. Pass ?confirm=true.",
            status=400,
        )

    try:
        if show_id:
            resp = tickets_table.query(KeyConditionExpression=Key("show_id").eq(show_id))
            items = resp.get("Items", [])
        else:
            resp = tickets_table.scan()
            items = resp.get("Items", [])
            while "LastEvaluatedKey" in resp:
                resp = tickets_table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
                items.extend(resp.get("Items", []))

        deleted = 0
        with tickets_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"show_id": item["show_id"], "seat_id": item["seat_id"]})
                deleted += 1

        return jsonify({"success": True, "deleted_count": deleted})
    except ClientError as e:
        logger.exception("delete_all_tickets failed")
        return error_response(str(e), 500)


@app.route("/api/tickets/<show_id>/<seat_id>", methods=["DELETE"])
def delete_single_ticket(show_id, seat_id):
    """Cancel one specific seat on a show (frees it up for re-booking)."""
    try:
        tickets_table.delete_item(
            Key={"show_id": show_id, "seat_id": seat_id},
            ConditionExpression="attribute_exists(seat_id)",
        )
        return jsonify({"success": True, "show_id": show_id, "seat_id": seat_id})
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return error_response("Ticket not found", 404)
        logger.exception("delete_single_ticket failed")
        return error_response(str(e), 500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
