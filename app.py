from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# The map is a static single-page app in web/. This app's only job is to serve
# those files. html=True serves web/index.html at "/" and lets the SPA resolve
# its own routes.
app = FastAPI()
app.mount("/", StaticFiles(directory="web", html=True), name="site")
