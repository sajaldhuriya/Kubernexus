powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
uv --version
.venv\Scripts\activate
uv pip install -r requirements.txt
python -m app.ingestion.processor DATA/true_data true 
python -m app.ingestion.processor DATA/true_data true --wipe
python -m app.ingestion.processor DATA/noisy_sample_10
uvicorn app.main:app --reload