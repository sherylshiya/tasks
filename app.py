from flask import Flask, render_template, request, redirect, url_for
import psycopg2
from azure.storage.blob import BlobServiceClient, BlobClient
import os
import uuid

app = Flask(__name__)

# Azure Blob Storage client setup
blob_conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(blob_conn_str)
container_name = "taskattachments"

def get_db_connection():
    conn_str = os.environ.get("AZURE_POSTGRESQL_CONNECTIONSTRING")
    try:
        if conn_str:
            conn = psycopg2.connect(conn_str)
        else:
            conn = psycopg2.connect(
                host=os.environ.get("DB_HOST", "taskmanager.postgres.database.azure.com"),
                database=os.environ.get("DB_NAME", "postgres"),
                user=os.environ.get("DB_USER", "your_pg_user"),
                password=os.environ.get("DB_PASS", "your_password"),
                port=os.environ.get("DB_PORT", 5432),
                sslmode='require'
            )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise

def init_db():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        attachment_url TEXT
                    );
                ''')
                conn.commit()
        print("DB initialized.")
    except Exception as e:
        print(f"DB initialization error: {e}")

with app.app_context():
    init_db()

@app.route("/")
def index():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, title, status, attachment_url FROM tasks ORDER BY id;")
                tasks = cur.fetchall()
        return render_template("index.html", tasks=tasks)
    except Exception as e:
        return f"Failed to load tasks: {e}", 500

@app.route("/add", methods=["GET", "POST"])
def add_task():
    if request.method == "POST":
        title = request.form.get("title")
        file = request.files.get("attachment")
        attachment_url = None

        if file:
            blob_name = str(uuid.uuid4()) + "_" + file.filename
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            blob_client.upload_blob(file)
            attachment_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{blob_name}"

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO tasks (title, status, attachment_url) VALUES (%s, %s, %s);",
                        (title, "Pending", attachment_url)
                    )
                    conn.commit()
            return redirect(url_for("index"))
        except Exception as e:
            return f"Failed to add task: {e}", 500
    return render_template("add_task.html")

@app.route("/complete/<int:task_id>")
def complete_task(task_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tasks SET status=%s WHERE id=%s;", ("Completed", task_id))
                conn.commit()
        return redirect(url_for("index"))
    except Exception as e:
        return f"Failed to mark task complete: {e}", 500

@app.route("/delete/<int:task_id>")
def delete_task(task_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tasks WHERE id=%s;", (task_id,))
                conn.commit()
        return redirect(url_for("index"))
    except Exception as e:
        return f"Failed to delete task: {e}", 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
