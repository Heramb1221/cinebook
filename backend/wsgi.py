"""WSGI entry point for gunicorn on EC2:  gunicorn -w 3 -b 0.0.0.0:5000 wsgi:app"""
from app import app

if __name__ == "__main__":
    app.run()
