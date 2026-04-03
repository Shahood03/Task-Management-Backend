from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.user import User

users_bp = Blueprint("users", __name__)


@users_bp.get("/")
@jwt_required()
def list_users():
    """Return all users except the current user (for task assignment)."""
    current_user_id = int(get_jwt_identity())

    search = (request.args.get("search") or "").strip()

    query = User.query.filter(User.id != current_user_id)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(User.username.ilike(like), User.email.ilike(like))
        )

    users = query.order_by(User.username).all()

    return jsonify({
        "users": [u.to_dict() for u in users],
        "count": len(users),
    }), 200


@users_bp.get("/<int:user_id>")
@jwt_required()
def get_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.to_dict()}), 200
