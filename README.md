# CineBook — Movie Ticket Booking Platform

A full-stack movie ticket booking app inspired by BookMyShow: browse now-showing movies,
pick a cinema/date/time, select seats on an interactive seat map, and check out.
Built with **Flask + boto3** on the backend, **DynamoDB** for storage, and a vanilla
HTML/CSS/JS frontend — deployable end-to-end on **AWS** (API Gateway, EC2, DynamoDB, S3).

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌────────────┐
│   Browser    │ ───> │  API Gateway  │ ───> │  EC2 (Flask  │ ───> │  DynamoDB   │
│ (S3 static   │      │  (HTTP API)   │      │  + gunicorn) │      │  (Tickets,  │
│  website)    │ <─── │               │ <─── │              │ <─── │  Movies,    │
└─────────────┘      └──────────────┘      └─────────────┘      │  Shows)    │
                                                                    └────────────┘
```

- **S3** hosts the static frontend (`index.html`, `styles.css`, `app.js`, posters) as a public website.
- **API Gateway** (HTTP API) is the stable public entry point; it proxies every request to the EC2 instance's Flask app, so the frontend never talks to a raw EC2 IP.
- **EC2** runs the Flask app under `gunicorn`, as a `systemd` service, with an IAM instance role (no embedded AWS keys).
- **DynamoDB** holds three tables: `Tickets` (bookings), `Movies` (catalogue), `Shows` (showtimes). No capacity planning needed — `PAY_PER_REQUEST` billing.

## Why duplicate seats are impossible

The `Tickets` table's primary key is **`(show_id, seat_id)`**. Every booking writes
each seat with:

```python
ConditionExpression = "attribute_not_exists(seat_id)"
```

inside a `transact_write_items` call. This makes the seat-assignment atomic and
race-proof **at the database layer** — not just in application code. If two people
click the same seat at the same instant, DynamoDB itself guarantees only one write
succeeds; the other gets a `409 Conflict` with the exact seat(s) that lost the race,
and the frontend automatically refreshes the seat map.

This is verified by an actual concurrency test (`backend/test_app.py`) that fires
10 simultaneous booking requests at the same seat — exactly 1 succeeds, 9 are
correctly rejected, every time.

## APIs

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/book` | Book 1–10 seats atomically (all-or-nothing transaction) |
| `GET` | `/api/tickets` | Get all tickets (optional `?show_id=`, `?movie_id=`, `?email=`) |
| `DELETE` | `/api/tickets?confirm=true` | Delete all tickets (optionally scoped by `?show_id=`) |
| `DELETE` | `/api/tickets/<show_id>/<seat_id>` | Cancel a single ticket |
| `GET` | `/api/movies` | List the movie catalogue |
| `GET` | `/api/shows/<movie_id>` | List showtimes for a movie |
| `GET` | `/api/seats/<show_id>` | Get booked seats for a specific show |
| `GET` | `/api/health` | Health check |

## Project structure

```
movie-booking/
├── backend/
│   ├── app.py              # Flask application (all routes + booking logic)
│   ├── wsgi.py              # gunicorn entry point for production
│   ├── requirements.txt
│   ├── test_app.py          # moto-based test suite incl. concurrency race test
│   └── local_server.py      # local dev server (mocked AWS) — for testing only
├── frontend/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── config.js            # <-- set API_BASE_URL here after deployment
│   ├── posters/              # original, copyright-free generated poster art
│   └── generate_posters.py
└── deployment/
    └── deploy.py             # boto3 script: provisions all AWS infra
```

## Deploying to AWS

### Prerequisites
- AWS credentials configured (`aws configure`, env vars, or an IAM role) with permissions for DynamoDB, EC2, S3, IAM, and API Gateway.
- Python 3.9+ and `pip install boto3` locally to run the deploy script.

### 1. Provision infrastructure

```bash
cd deployment
pip install boto3
python3 deploy.py up --frontend-dir ../frontend
```

This will:
1. Create the `Tickets`, `Movies`, `Shows` DynamoDB tables and seed demo data.
2. Create and configure an S3 bucket for static website hosting, and upload the frontend.
3. Launch a `t3.micro` EC2 instance (free-tier eligible) with an IAM role for DynamoDB access, in a security group opening ports 22/80/5000.
4. Create an API Gateway HTTP API pointed at the EC2 instance.

At the end it prints the S3 website URL, the API Gateway endpoint, and the EC2 IP.

### 2. Upload and start the backend on EC2

```bash
scp -i movie-booking-key.pem -r ../backend/* ec2-user@<EC2_PUBLIC_IP>:/opt/movie-booking/
ssh -i movie-booking-key.pem ec2-user@<EC2_PUBLIC_IP> \
  'cd /opt/movie-booking && sudo pip3 install -r requirements.txt && sudo systemctl enable --now movie-booking'
```

### 3. Point the frontend at your API

Edit `frontend/config.js`:

```js
const API_BASE_URL = "https://xxxxx.execute-api.ap-south-1.amazonaws.com";
```

Then re-upload just that file:

```bash
aws s3 cp ../frontend/config.js s3://<your-bucket-name>/config.js
```

### Check status / tear down

```bash
python3 deploy.py status   # see current resource states & endpoints
python3 deploy.py down     # delete everything (asks for confirmation)
```

## Running locally (no AWS account needed)

The backend can run fully offline against a mocked DynamoDB using `moto`, which is
how this project was developed and tested:

```bash
cd backend
pip install -r requirements.txt moto pytest
python3 test_app.py          # run the full test suite (incl. race condition test)
python3 local_server.py      # start a local server on :5000 with seeded demo data
```

Then in another terminal:

```bash
cd frontend
python3 -m http.server 8080
```

`config.js` already defaults to `http://localhost:5000` for this workflow — open
`http://localhost:8080` in your browser.

## Notes

- Poster art in `frontend/posters/` is original, procedurally generated SVG artwork — no copyrighted images are used, so this is safe to use as a portfolio/demo piece.
- The demo catalogue uses original (non-trademarked) movie titles for the same reason.
- `DELETE /api/tickets` requires an explicit `?confirm=true` to prevent accidental wipes from being triggered by a stray request.
