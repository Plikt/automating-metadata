from flask import Flask, request, jsonify
# Import your script
from .langchain_orcid2 import run as run_langchain

app = Flask(__name__)

@app.route('/invoke-script', methods=['POST'])
def invoke_script():
    data = request.json  # Assuming JSON data is sent from the web app
    pdf = data.get("pdf")
    doi = data.get("doi")
    # Call your script with the appropriate inputs

    if doi is not None:
        output = run_langchain(pdf, doi)
    else:
        output = run_langchain(pdf)
    return jsonify({'output': output})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
