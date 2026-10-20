from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from root import db

##
## DO NOT MODIFY THIS FILE, and DO NOT modify 'people' table:
## treat it as 'read-only'. It will be updated (externally) with
## list of staff/students (on the production server)
##

class Person(db.Model):
    """A student or staff member (same schema as the SortingRenertRounds 'people' table)."""

    __tablename__ = "people"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    pronoun: Mapped[str | None] = mapped_column(Text)    # "M", "F" or NULL
    grade: Mapped[str | None] = mapped_column(Text)      # "4".."12", "Staff" or NULL
    honorific: Mapped[str | None] = mapped_column(Text)  # e.g. "Mr. Gordon"

    def __repr__(self):
        return f"<Person {self.email}>"
