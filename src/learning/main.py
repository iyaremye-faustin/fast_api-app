from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello World"}

def dev():
    import uvicorn
    uvicorn.run("my_api.main:app", reload=True)