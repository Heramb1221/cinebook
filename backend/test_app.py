"""
Local test harness using moto to mock DynamoDB.
Verifies:
  1. Basic booking works
  2. Duplicate seat booking is rejected (sequential)
  3. Concurrent requests for the SAME seat -> only one wins (race condition test)
  4. get_tickets / delete_tickets work as expected
"""
import os
import sys
import json
import threading

os.environ["AWS_REGION"] = "ap-south-1"
os.environ["TICKETS_TABLE"] = "Tickets"
os.environ["MOVIES_TABLE"] = "Movies"
os.environ["SHOWS_TABLE"] = "Shows"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"

from moto import mock_aws

@mock_aws
def run_tests():
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

    sys.path.insert(0, os.path.dirname(__file__))
    import app as appmodule
    client = appmodule.app.test_client()

    payload = {
        "show_id": "tt001#PVR#2026-07-01#19:30",
        "movie_id": "tt001",
        "movie_title": "Inception",
        "theatre": "PVR Lower Parel",
        "show_date": "2026-07-01",
        "show_time": "19:30",
        "seats": [{"seat_id": "G12", "seat_type": "Premium", "price": 350}],
        "customer_name": "Heramb",
        "customer_email": "heramb@example.com",
    }

    # 1. First booking should succeed
    r1 = client.post("/api/book", json=payload)
    assert r1.status_code == 201, f"Expected 201, got {r1.status_code}: {r1.get_json()}"
    print("TEST 1 PASSED: first booking succeeded ->", r1.get_json()["booking_id"])

    # 2. Booking the SAME seat again should fail with 409
    r2 = client.post("/api/book", json=payload)
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.get_json()}"
    body2 = r2.get_json()
    assert "G12" in body2["conflicted_seats"]
    print("TEST 2 PASSED: duplicate seat booking rejected ->", body2)

    # 3. Concurrency race: fire 10 threads at the SAME seat simultaneously
    race_payload = dict(payload)
    race_payload["show_id"] = "tt001#PVR#2026-07-01#21:00"
    race_payload["seats"] = [{"seat_id": "A1", "seat_type": "Standard", "price": 200}]

    results = []
    lock = threading.Lock()

    def attempt_booking():
        r = client.post("/api/book", json=race_payload)
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=attempt_booking) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    success_count = results.count(201)
    conflict_count = results.count(409)
    assert success_count == 1, f"Expected exactly 1 success, got {success_count}. Results: {results}"
    assert conflict_count == 9, f"Expected 9 conflicts, got {conflict_count}. Results: {results}"
    print(f"TEST 3 PASSED: race condition handled correctly -> {success_count} success, {conflict_count} conflicts")

    # 4. Multi-seat booking, then get all tickets
    multi_payload = dict(payload)
    multi_payload["show_id"] = "tt002#INOX#2026-07-02#18:00"
    multi_payload["movie_id"] = "tt002"
    multi_payload["movie_title"] = "Interstellar"
    multi_payload["seats"] = [
        {"seat_id": "B1", "seat_type": "Standard", "price": 200},
        {"seat_id": "B2", "seat_type": "Standard", "price": 200},
    ]
    r4 = client.post("/api/book", json=multi_payload)
    assert r4.status_code == 201, r4.get_json()
    print("TEST 4 PASSED: multi-seat booking ->", len(r4.get_json()["tickets"]), "tickets")

    # 5. Get all tickets
    r5 = client.get("/api/tickets")
    assert r5.status_code == 200
    total = r5.get_json()["count"]
    assert total == 4, f"Expected 4 total tickets (1+1+2), got {total}"
    print(f"TEST 5 PASSED: get all tickets -> {total} tickets found")

    # 6. Delete all tickets requires confirm flag
    r6a = client.delete("/api/tickets")
    assert r6a.status_code == 400
    print("TEST 6a PASSED: delete without confirm rejected")

    r6b = client.delete("/api/tickets?confirm=true")
    assert r6b.status_code == 200
    deleted = r6b.get_json()["deleted_count"]
    assert deleted == 4, f"Expected 4 deleted, got {deleted}"
    print(f"TEST 6b PASSED: delete all tickets -> {deleted} deleted")

    r7 = client.get("/api/tickets")
    assert r7.get_json()["count"] == 0
    print("TEST 7 PASSED: tickets table empty after delete")

    print("\nALL TESTS PASSED ✅")


if __name__ == "__main__":
    run_tests()
