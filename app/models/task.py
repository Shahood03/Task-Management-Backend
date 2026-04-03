from app import db
from datetime import datetime, timezone


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("todo", "in_progress", "done", name="task_status"),
        nullable=False,
        default="todo",
    )
    priority = db.Column(
        db.Enum("low", "medium", "high", name="task_priority"),
        nullable=False,
        default="medium",
    )
    due_date = db.Column(db.Date, nullable=True)

    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def is_assigned(self) -> bool:
        return self.assignee_id is not None

    def to_dict(self, current_user_id: int = None):
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "is_assigned": self.is_assigned,
            "creator_id": self.creator_id,
            "creator": self.creator.to_dict() if self.creator else None,
            "assignee_id": self.assignee_id,
            "assignee": self.assignee.to_dict() if self.assignee else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        if current_user_id:
            data["role"] = self._get_user_role(current_user_id)

        return data

    def _get_user_role(self, user_id: int) -> str:
        if not self.is_assigned:
            return "owner"
        if user_id == self.creator_id:
            return "assigner"
        if user_id == self.assignee_id:
            return "assignee"
        return "viewer"
