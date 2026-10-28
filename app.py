# app.py
import os
import logging
from flask import Flask
from config import Config
from database.db import init_db

# Import Blueprints (these should expose Blueprint instances named `main`, `admin`, `student`)
from controllers.main_routes import main
from controllers.admin_routes import admin
from controllers.student_routes import student

# ------------ logging ------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    # Initialize MongoDB (or other DB). Log any errors but let app start so you can see them.
    try:
        init_db(app)
        logger.info("Database initialized.")
    except Exception as e:
        logger.exception("Failed to initialize database: %s", e)

    # Register Blueprints
    # If your blueprints already set url_prefix inside their files, you can register like below.
    app.register_blueprint(main)
    app.register_blueprint(admin)
    app.register_blueprint(student)

    # Example health route (optional)
    @app.route("/_health")
    def health():
        return "OK", 200

    return app

if __name__ == "__main__":
    app = create_app()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")

    logger.info("Server starting on port %s", port)
    app.run(host=host, port=port, debug=debug)

    logger.info("Server starting → http://%s:%s", host, port)
    logger.info("Access on Mobile → http://<YOUR_PC_IP>:%s (example: http://192.168.1.10:%s)", port, port)

    # Run dev server (development only)
    app.run(host=host, port=port, debug=debug)
