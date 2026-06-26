# NexusJobs Backend 🚀

A robust, high-performance Job Board backend built using **FastAPI** and **Python**, featuring a dynamic frontend template system and automated relational data persistence. This application is fully structured, container-ready, and deployed live in the cloud.

🔗 **Live Demo:** [https://nexus-jobs-yyvy.onrender.com](https://nexus-jobs-yyvy.onrender.com)

---

## 🛠️ Tech Stack & Architecture

* **Backend Framework:** FastAPI (Python) - Utilizing asynchronous routing and automatic OpenAPI/Swagger documentation generation.
* **Database & ORM:** SQLite for lightweight, reliable relational data storage, managed seamlessly via **SQLAlchemy** ORM.
* **Data Validation:** **Pydantic** schemas for strict, type-safe request and response payload validation.
* **Frontend Integration:** **Jinja2** templates for dynamic rendering of HTML layouts directly from backend contexts.
* **Deployment:** Hosted on **Render** cloud infrastructure with automated continuous deployment.

---

## 📂 Project Structure

```text
├── templates/          # Dynamic HTML frontend layouts (Jinja2)
├── database.py         # SQLAlchemy engine setup and session configuration
├── main.py             # FastAPI core application instance and route definitions
├── models.py           # Relational database models (SQLAlchemy)
├── schemas.py          # Data validation models (Pydantic)
├── requirements.txt    # Project dependencies and environment packages
└── nexus_jobs.db       # Local SQLite database file (ignored in production)
