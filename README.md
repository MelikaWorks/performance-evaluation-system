# Performance Evaluation System (Django)

A web-based performance evaluation platform built with Django, designed for multi-organization environments (holding / factory / department groups) with role-based access, workflow approvals, and manager/admin reporting.

## Key Features
- Multi-organization scoping (Holding, Factory, DepartmentGroup)
- Role-based access for Admins and Managers
- Evaluation workflow and approval states (signatures and audit-ready structure)
- Manager dashboards and reports (including print-friendly views)
- CSV / PDF / Print-ready reporting paths
- Structured import and maintenance scripts

## Tech Stack
- Python / Django
- PostgreSQL (intended for production)
- HTML, CSS, JavaScript (server-rendered templates)
- Chart.js for reporting visuals
- SharePoint Lists, Libraries, and Custom Views
- Portfolio & Resource Management Concepts

## Repository Structure
- `core/` – Main application logic (models, views, approvals, workflow, templates, static files)
- `project/` – Django project configuration (settings, URLs, WSGI/ASGI)
- `scripts/` – Utility scripts for imports, analysis, and maintenance
- `docs/` – Technical documentation and design notes

### Database Design
The database schema is defined and managed through Django models and migrations, ensuring consistency across environments.


## Organizational Coding Structure

To improve consistency and avoid relying on free-text values, the system uses fixed numeric codes for organizational units, job titles, and job levels.

This approach was introduced because relying only on Persian display names caused several issues:

- Different spellings or wording for the same title or unit
- Difficulty in filtering, reporting, and workflow routing
- Hard-coded dependencies on Persian text values
- Reduced maintainability when names change over time
- Inconsistent mapping between employees, managers, units, and evaluations

Instead of using display text as the primary identifier, the application uses stable internal codes. Display names can change later without affecting business logic, permissions, reports, or workflow behavior.

### Benefits

- Consistent and normalized data across the system
- Easier filtering, reporting, and manager assignment
- Safer workflow routing and approval logic
- Better support for future multi-organization expansion
- Easier maintenance if department or title names are renamed

---

### Unit Codes

Each organizational unit has a unique code:

| Code | Unit |
|------|------|
| 202 | Lubricants |
| 207 | Finance |
| 208 | Quality / R&D |
| 210 | Electrical & Instrumentation |
| 212 | Production |
| 213 | Warehouse |
| 216 | Security |
| 217 | Civil |
| 218 | IT |
| 219 | Logistics |
| 222 | Quality Control |
| 307 | Mechanical |

These codes are used in employee profiles, evaluation routing, reports, and manager-level access control.

---

### Job Title / Job Level Codes

The system also defines stable codes for job hierarchy levels:

| Code | Job Title |
|------|------|
| 900 | Factory Manager |
| 901 | Unit Manager |
| 902 | Supervisor / Head |
| 903 | Team Lead / Shift Lead |
| 904 | Responsible Person |
| 905 | Employee |
| 906 | Specialist |
| 907 | Senior Specialist / Lead Specialist |
| 908 | Technician |

> Note: The visible job title may change in the future, but its code remains constant inside the system.

---

### Example Usage

```python
if employee.job_level_code == 900:
    # Factory Manager access
    ...

if employee.unit_code == 218:
    # IT department logic
    ...
```
By using stable internal codes instead of raw text values, the system becomes easier to maintain, safer for workflow and permission logic, and more scalable for future organizational and multi-company changes.


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
Python (Django) • PostgreSQL • System Design • Agile

🔗 [LinkedIn](https://www.linkedin.com/in/melika-mehranpour-41b627161/) | [GitHub](https://github.com/MelikaWorks)

## License
See the [LICENSE](LICENSE) file for license information.
