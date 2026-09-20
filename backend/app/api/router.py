from fastapi import APIRouter
from app.api.routes import projects,media,annotations,prompts,tracking,exports,stats
router=APIRouter(prefix='/api')
for x in (projects.router,media.router,annotations.router,prompts.router,tracking.router,exports.router,stats.router):router.include_router(x)
