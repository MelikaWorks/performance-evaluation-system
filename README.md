# Performance Evaluation System (Django)

A web-based performance evaluation platform built with Django, designed for multi-organization environments (holding / factory / department groups) with role-based access, workflow approvals, and manager/admin reporting.

## Key Features
- Multi-organization scoping (Holding, Factory, DepartmentGroup)
- Role-based access for Admins and Managers
- Evaluation workflow & approval states (signatures and audit-ready structure)
- Manager dashboards and reports (including print-friendly views)
- CSV / PDF / Print-ready reporting paths
- Structured import and maintenance scripts

## Tech Stack
- Python / Django
- PostgreSQL (intended for production)
- HTML, CSS, JavaScript (server-rendered templates)
- Chart.js for reporting visuals

## Repository Structure
- `core/` – Main application logic (models, views, approvals, workflow, templates, static files)
- `project/` – Django project configuration (settings, URLs, WSGI/ASGI)
- `scripts/` – Utility scripts for imports, analysis, and maintenance
- `docs/` – Technical documentation and design notes

## Local Setup
1. Create and activate a virtual environment

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables locally (`.env` is excluded from version control)

4. Run migrations and start the server:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

## Notes
- Sensitive data and local artifacts are excluded using `.gitignore`
- The project follows a clean commit history and modular structure

## Project Management
Project lifecycle was managed using **Azure DevOps**, including backlog tracking, task breakdown, and release coordination.

## Author

👩‍💻 **Melika Mehranpour**  
Senior Software Engineer | Backend & Enterprise Systems  
Python (Django) • ASP.NET Core • PostgreSQL • System Design • Agile

🔗 [LinkedIn]([https://www.linkedin.com/in/melika-mehranpour](https://www.linkedin.com/in/melika-mehranpour-41b627161/)) | [GitHub](https://github.com/MelikaWorks)

## License
See `LICENSE` for license information.
