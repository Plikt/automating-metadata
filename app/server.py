from flask import Flask, request, jsonify
import os
# Import your script
from .langchain_orcid2 import run as run_langchain
from .auth import validate_api_key

# Read environment variables
cr_mailto = os.getenv('CR_MAILTO')
pyalex_email = os.getenv('PYALEX_EMAIL')

app = Flask(__name__)

@app.route('/invoke-script', methods=['POST'])
@validate_api_key

def invoke_script():
    data = request.json  # Assuming JSON data is sent from the web app
    pdf = data.get("pdf")
    doi = data.get("doi")
    # Call your script with the appropriate inputs

    if doi is not None:
        output = run_langchain(pdf, doi, cr_mailto, pyalex_email)
    elif pdf is None and doi is not None: 
        output = run_langchain(doi, cr_mailto, pyalex_email)
    else: 
        output = run_langchain(pdf, cr_mailto, pyalex_email)
    return jsonify({'output': output})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)