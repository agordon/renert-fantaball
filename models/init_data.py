from sqlalchemy.exc import SQLAlchemyError

from models.people import Person
from root import app, db


# Minimal starting data. Add more rows here as needed.
INITIAL_PEOPLE = [
    {"email": "john.doe@example.com", "pronoun": "M", "grade": "12", "honorific": None},
]


def init_data():
    """Insert the initial people, skipping any whose email is already in the table."""
    try:
        for data in INITIAL_PEOPLE:
            existing = db.session.scalars(db.select(Person).where(Person.email == data["email"])).first()
            if existing is None:
                db.session.add(Person(**data))
                app.logger.info(f"init_data: added person {data['email']}")
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        app.logger.error(f"init_data failed: {str(exc)}")
        raise
