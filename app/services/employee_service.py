"""Employee CRUD operations."""

from app.extensions import db
from app.models.employee import Employee


def create_employee(name: str, email: str, position: str, password: str, is_active: bool) -> Employee:
    employee = Employee(name=name, email=email, position=position, is_active=is_active, password_hash="")
    employee.set_password(password)
    db.session.add(employee)
    db.session.commit()
    return employee


def update_employee(employee: Employee, name: str, email: str, position: str, is_active: bool) -> Employee:
    employee.name, employee.email, employee.position, employee.is_active = name, email, position, is_active
    db.session.commit()
    return employee


def delete_employee(employee: Employee) -> None:
    db.session.delete(employee)
    db.session.commit()
