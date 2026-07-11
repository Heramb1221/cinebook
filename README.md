# CineBook — Movie Ticket Booking Platform

> Cloud-native movie ticket booking platform inspired by BookMyShow, built with Flask, DynamoDB, and AWS. Designed to demonstrate atomic seat booking, scalable cloud architecture, and production-inspired backend engineering.

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-Backend-black?style=for-the-badge&logo=flask)
![AWS](https://img.shields.io/badge/AWS-Cloud-FF9900?style=for-the-badge&logo=amazonaws)
![DynamoDB](https://img.shields.io/badge/DynamoDB-NoSQL-4053D6?style=for-the-badge&logo=amazondynamodb)
![API Gateway](https://img.shields.io/badge/API-Gateway-orange?style=for-the-badge&logo=amazonapigateway)
![Status](https://img.shields.io/badge/Status-Production--Architecture%20Prototype-purple?style=for-the-badge)

---

# Live Demo

The cloud deployment is currently offline to avoid unnecessary AWS costs.

The project remains fully deployable using the included infrastructure automation script.

---

# About The Project

CineBook is a full-stack cloud-native movie ticket booking platform built to explore real-world backend engineering concepts on AWS.

Users can browse movies, view available shows, select seats from an interactive seat map, and complete bookings through a REST API backed by DynamoDB.

Unlike traditional booking systems that rely on database locks, CineBook uses DynamoDB transactions and conditional writes to guarantee atomic seat booking even under concurrent requests.

The infrastructure is provisioned programmatically using boto3 and includes S3 static hosting, EC2, API Gateway, IAM Roles, and DynamoDB.

---

# Project Type

| Attribute | Value |
|---|---|
| Category | Cloud Native Web Application |
| Architecture | Flask REST Backend + Static Frontend |
| Database | Amazon DynamoDB |
| Cloud Platform | AWS |
| Deployment | EC2 + API Gateway + S3 |
| Infrastructure | boto3 Automation |

---

# Project Status

**Production Architecture Learning Project**

Implemented:

- Atomic seat booking
- REST API backend
- AWS infrastructure provisioning
- Offline development using Moto
- Automated concurrency testing

---

# Why I Built This

Most movie booking tutorials focus only on CRUD functionality.

This project explores how cloud-native services can solve real engineering problems such as concurrent bookings, infrastructure automation, IAM-based authentication, and scalable backend deployment without relying on traditional SQL locking mechanisms.

---

# Features

## Core Features

- Browse movie catalogue
- View movie showtimes
- Interactive seat selection
- Book up to 10 seats atomically
- Cancel bookings
- View booking history

## Engineering Features

- Infrastructure provisioning using boto3
- API Gateway reverse proxy
- Gunicorn production deployment
- Health check endpoint
- Automated demo data seeding

## Developer Experience

- Moto-powered offline testing
- Automated deployment
- One-command teardown
- Local development server

---

# Tech Stack

## Frontend

- HTML5
- CSS3
- JavaScript

## Backend

- Flask
- Gunicorn
- boto3

## AWS Services

- Amazon EC2
- Amazon S3
- Amazon API Gateway
- Amazon DynamoDB
- IAM

---

# Architecture

```text
Browser (S3 Static Website)
        │
        ▼
API Gateway
        │
        ▼
EC2 (Flask + Gunicorn)
        │
        ▼
Amazon DynamoDB
```

---

# Booking Lifecycle

```text
User selects seats
      │
      ▼
POST /api/book
      │
      ▼
Flask validates request
      │
      ▼
DynamoDB Transaction
      │
      ├── Seat exists → Reject
      └── Seat available → Commit
      │
      ▼
Booking confirmed
```

---

# Concurrency Handling

The `Tickets` table uses `(show_id, seat_id)` as the primary key.

Each booking executes a DynamoDB `transact_write_items` operation with:

```python
ConditionExpression="attribute_not_exists(seat_id)"
```

This guarantees only one request can successfully reserve a seat. Competing requests automatically fail with HTTP 409 Conflict.

A concurrency test submits ten simultaneous booking requests for the same seat. Exactly one succeeds while the remaining requests fail, verifying the implementation.

---

# REST API

| Method | Endpoint | Description |
|---|---|---|
| POST | /api/book | Atomic booking |
| GET | /api/tickets | View tickets |
| DELETE | /api/tickets | Delete tickets |
| DELETE | /api/tickets/{show}/{seat} | Cancel booking |
| GET | /api/movies | Movie catalogue |
| GET | /api/shows/{movie} | Showtimes |
| GET | /api/seats/{show} | Reserved seats |
| GET | /api/health | Health check |

---

# Folder Structure

```text
movie-booking/
├── backend/
├── frontend/
├── deployment/
└── README.md
```

---

# Installation

```bash
git clone <repo-url>
cd movie-booking
pip install -r backend/requirements.txt
```

---

# Deployment

```bash
cd deployment
python deploy.py up --frontend-dir ../frontend
```

Then upload the backend to EC2 and update `frontend/config.js` with the API Gateway endpoint.

---

# Local Development

```bash
cd backend
pip install -r requirements.txt moto pytest
python test_app.py
python local_server.py
```

Frontend:

```bash
cd frontend
python -m http.server 8080
```

---

# Performance Considerations

## Optimizations

- Atomic transactions
- Pay-per-request DynamoDB
- Static frontend hosting
- IAM authentication
- API Gateway abstraction

## Current Bottlenecks

- Single EC2 instance
- No caching
- No load balancer
- No auto scaling

---

# Security Considerations

| Concern | Implementation |
|---|---|
| AWS Credentials | IAM Role |
| Duplicate Booking | DynamoDB Transactions |
| Atomic Writes | transact_write_items |
| Public API | API Gateway |

---

# Tradeoffs & Limitations

| Decision | Tradeoff |
|---|---|
| EC2 | Easier deployment but always-on cost |
| DynamoDB | Limited querying compared to SQL |
| Flask | Simple architecture but monolithic |

---

# Known Issues

- No authentication
- No payment gateway
- No rate limiting
- No reservation timeout
- Single-instance deployment

---

# Technical Debt

- Service layer separation
- Improved configuration validation
- More automated tests
- Docker support

---

# Challenges Faced

- Atomic booking implementation
- Concurrent request handling
- AWS infrastructure automation
- Offline cloud testing

---

# What I Learned

- DynamoDB transactions
- IAM Roles
- API Gateway
- Gunicorn deployment
- Infrastructure automation
- Cloud-native backend design

---


# Contact

**Heramb Chaudhari**

[![GitHub](https://img.shields.io/badge/GitHub-Heramb1221-black?style=for-the-badge&logo=github)](https://github.com/Heramb1221)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Heramb%20Chaudhari-blue?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/heramb-chaudhari)

[![Email](https://img.shields.io/badge/Email-hchaudhari1221%40gmail.com-red?style=for-the-badge&logo=gmail)](mailto:hchaudhari1221@gmail.com)

---

Built to explore production-inspired cloud architecture using Flask, DynamoDB, API Gateway, EC2, S3, and boto3.
