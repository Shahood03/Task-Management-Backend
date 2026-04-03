from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_
from app import db
from app.models.task import Task
from app.models.user import User
from datetime import date

tasks_bp = Blueprint("tasks", __name__)

VALID_STATUSES = {"todo", "in_progress", "done"}
VALID_PRIORITIES = {"low", "medium", "high"}


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@tasks_bp.get("/")
@jwt_required()
def list_tasks():
    user_id = int(get_jwt_identity())

    # Filter params
    status = request.args.get("status")
    priority = request.args.get("priority")
    task_type = request.args.get("type")  # personal | assigned

    query = Task.query.filter(
        or_(Task.creator_id == user_id, Task.assignee_id == user_id)
    )

    if task_type == "personal":
        query = query.filter(Task.assignee_id.is_(None), Task.creator_id == user_id)
    elif task_type == "assigned":
        query = query.filter(Task.assignee_id.isnot(None))

    if status and status in VALID_STATUSES:
        query = query.filter(Task.status == status)

    if priority and priority in VALID_PRIORITIES:
        query = query.filter(Task.priority == priority)

    tasks = query.order_by(Task.created_at.desc()).all()

    return jsonify({
        "tasks": [t.to_dict(current_user_id=user_id) for t in tasks],
        "count": len(tasks),
    }), 200


@tasks_bp.post("/")
@jwt_required()
def create_task():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    status = data.get("status", "todo")
    if status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {sorted(VALID_STATUSES)}"}), 400

    priority = data.get("priority", "medium")
    if priority not in VALID_PRIORITIES:
        return jsonify({"error": f"priority must be one of {sorted(VALID_PRIORITIES)}"}), 400

    due_date = _parse_date(data.get("due_date"))

    assignee_id = data.get("assignee_id")
    if assignee_id is not None:
        assignee_id = int(assignee_id)
        if assignee_id == user_id:
            return jsonify({"error": "Cannot assign task to yourself — create a personal task instead"}), 400
        assignee = db.session.get(User, assignee_id)
        if not assignee:
            return jsonify({"error": "Assignee not found"}), 404

    task = Task(
        title=title,
        description=(data.get("description") or "").strip() or None,
        status=status,
        priority=priority,
        due_date=due_date,
        creator_id=user_id,
        assignee_id=assignee_id,
    )
    db.session.add(task)
    db.session.commit()

    return jsonify({
        "message": "Task created successfully",
        "task": task.to_dict(current_user_id=user_id),
    }), 201


@tasks_bp.get("/<int:task_id>")
@jwt_required()
def get_task(task_id):
    user_id = int(get_jwt_identity())
    task = _get_accessible_task(task_id, user_id)

    if task is None:
        return jsonify({"error": "Task not found or access denied"}), 404

    return jsonify({"task": task.to_dict(current_user_id=user_id)}), 200


@tasks_bp.put("/<int:task_id>")
@jwt_required()
def update_task(task_id):
    user_id = int(get_jwt_identity())
    task = _get_accessible_task(task_id, user_id)

    if task is None:
        return jsonify({"error": "Task not found or access denied"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    role = task._get_user_role(user_id)

    # Assignee: can only update status
    if role == "assignee":
        if "status" in data:
            new_status = data["status"]
            if new_status not in VALID_STATUSES:
                return jsonify({"error": f"status must be one of {sorted(VALID_STATUSES)}"}), 400
            task.status = new_status
        forbidden = {"title", "description", "priority", "due_date", "assignee_id"} & data.keys()
        if forbidden:
            return jsonify({"error": f"Assignee cannot modify: {', '.join(sorted(forbidden))}"}), 403

    # Assigner (creator of assigned task): can update due_date only (not status)
    elif role == "assigner":
        if "status" in data:
            return jsonify({"error": "Assigner cannot update task status"}), 403
        if "due_date" in data:
            due_date = _parse_date(data["due_date"])
            task.due_date = due_date
        forbidden = {"title", "description", "priority", "assignee_id"} & data.keys()
        if forbidden:
            return jsonify({"error": f"Assigner cannot modify: {', '.join(sorted(forbidden))}"}), 403

    # Owner (personal task creator): can update all fields
    elif role == "owner":
        if "title" in data:
            title = (data["title"] or "").strip()
            if not title:
                return jsonify({"error": "title cannot be empty"}), 400
            task.title = title
        if "description" in data:
            task.description = (data["description"] or "").strip() or None
        if "status" in data:
            if data["status"] not in VALID_STATUSES:
                return jsonify({"error": f"status must be one of {sorted(VALID_STATUSES)}"}), 400
            task.status = data["status"]
        if "priority" in data:
            if data["priority"] not in VALID_PRIORITIES:
                return jsonify({"error": f"priority must be one of {sorted(VALID_PRIORITIES)}"}), 400
            task.priority = data["priority"]
        if "due_date" in data:
            task.due_date = _parse_date(data["due_date"])
    else:
        return jsonify({"error": "Access denied"}), 403

    # Refresh updated_at manually (SQLite doesn't trigger onupdate)
    from datetime import datetime, timezone
    task.updated_at = datetime.now(timezone.utc)

    db.session.commit()

    return jsonify({
        "message": "Task updated successfully",
        "task": task.to_dict(current_user_id=user_id),
    }), 200


@tasks_bp.delete("/<int:task_id>")
@jwt_required()
def delete_task(task_id):
    user_id = int(get_jwt_identity())
    task = _get_accessible_task(task_id, user_id)

    if task is None:
        return jsonify({"error": "Task not found or access denied"}), 404

    if task.creator_id != user_id:
        return jsonify({"error": "Only the task creator can delete it"}), 403

    db.session.delete(task)
    db.session.commit()

    return jsonify({"message": "Task deleted successfully"}), 200


def _get_accessible_task(task_id: int, user_id: int):
    """Return task only if user is creator or assignee."""
    return Task.query.filter(
        Task.id == task_id,
        or_(Task.creator_id == user_id, Task.assignee_id == user_id),
    ).first()
