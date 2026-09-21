from fastapi import APIRouter
from app.api.routes import projects,media,annotations,prompts,tracking,exports,stats,settings as settings_routes
router=APIRouter(prefix='/api')
for x in (projects.router,media.router,annotations.router,prompts.router,tracking.router,exports.router,stats.router,settings_routes.router):router.include_router(x)
