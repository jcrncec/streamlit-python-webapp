# LOCAL
    # Install dependencies:
    pip install streamlit pandas pydeck lxml

    # How to run
    streamlit run app.py

    # If you get an error try with venv
    python3 -m venv .venv         
    source .venv/bin/activate

# DOCKER
    # Build the Docker image
    docker build -t streamlit-kml-app .

    # Run the container
    docker run -p 8501:8501 streamlit-kml-app
