from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello World"}

def dev():
    import uvicorn
    uvicorn.run("learning.main:app", reload=True)