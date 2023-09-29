"""
Use of openai plus langchain for processing information in a pdf
Generated using chatGPT for incorporating asyncio for concurrent running of prompts
Generated by pasting my code from the analysis_v3 script with the following question:
Can you modify the below python code to incorporate asyncio to allow concurrent running of the paper_search() function?
"""
import sys 
import os
from pathlib import Path  # directory setting
import asyncio # For async asking of prompts
import json

import httpx  # for elsevier and semantic scholar api calls
from habanero import Crossref, cn  # Crossref database accessing
from dotenv import load_dotenv, find_dotenv  # loading in API keys
from langchain.document_loaders import PyPDFLoader, PyMuPDFLoader # document loader import
from langchain.chat_models import ChatOpenAI  # LLM import
from langchain import LLMChain  # Agent import
from langchain.prompts.chat import ( # prompts for designing inputs
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate
)
from langchain.indexes import VectorstoreIndexCreator
import fitz #pdf reading library
import json
from pyalex import Works #, Authors, Sources, Institutions, Concepts, Publishers, Funders
import pyalex
from demo import read_single

#from ..Server.PDFDataExtractor.pdfdataextractor.demo import read_single
sys.path.append(os.path.abspath("/Users/desot1/Dev/automating-metadata/Server/PDFDataExtractor/pdfdataextractor"))
pyalex.config.email = "ellie@desci.com"

# Load in API keys from .env file
load_dotenv(find_dotenv())


def openalex(doi): 
    dict = Works()[doi]
    return dict


def paper_data_json_single(doi):
    """
    Create a json output file for a single paper using the inputed identifier.
    Only using a DOI string at the moment
    File constructed based on the info in metadata_formatting_categories.md

    Inputs:
    doi - string, DOI string for the paper/publication of interest
    output - string, path of where to save json output
    ---
    output:
    dictionary, conversion to json and writing to file
    """
    #%% Setting up info for usage of API's
    # define crossref object
    cr = Crossref()  
    cr.mailto = 'desotaelianna@gmail.com'
    cr.ua_string = 'Python/Flask script for use in Desci Nodes publication information retrieval.'

    # Elsevier API key
    apikey = os.getenv("apikey")
    client = httpx.Client()


    #%% Info from Crossref
    r = cr.works(ids = f'{doi}')  # Crossref search using DOI, "r" for request

    title = r['message']['title'][0]
    type = r['message']['type']
    pub_name = r['message']['container-title'][0]
    pub_date = r['message']['published']['date-parts'][0]
    #subject = r['message']['subject']

    inst_names = []  # handling multiple colleges, universities
    authors = []  # for handling multiple authors

    for i in r['message']['author']:
        authors.append(i['given'] + ' ' + i['family'])
        try:
            name = (i['affiliation'][0]['name'])
            if name not in inst_names:
                inst_names.append(name)
        except:
            continue

    if len(inst_names) == 0:  # returning message if no institutions returned by Crossref, may be able to get with LLM
        inst_names = "No institutions returned by CrossRef"


    refs = []
    for i in r['message']['reference']:
        try:
            refs.append(i['DOI'])
        except:
            refs.append(f"{i['key']}, DOI not present")
        
    url_link = r['message']['URL']
    

    #%% Info from Elsevier
    format = 'application/json'
    view ="FULL"
    url = f"https://api.elsevier.com/content/article/doi/{doi}?APIKey={apikey}&httpAccept={format}&view={view}"
    with httpx.Client() as client:
        r=client.get(url)
    
    json_string = r.text
    d = json.loads(json_string)  # "d" for dictionary

    try:
        d['full-text-retrieval-response']
        scopus_id = d['full-text-retrieval-response']['scopus-id']
        abstract = d['full-text-retrieval-response']['coredata']['dc:description']

        """keywords = []
        for i in d['full-text-retrieval-response']['coredata']['dcterms:subject']:
            keywords.append(i['$'])"""

        original_text = d['full-text-retrieval-response']['originalText']
    except:
        scopus_id = 'None, elsevier error'
        abstract = 'None, elsevier error'
        keywords = ['None, elsevier error']
        original_text = 'None, elsevier error'
    

    #%% Info from Semantic Scholar
    url = f'https://api.semanticscholar.org/graph/v1/paper/{doi}/?fields=fieldsOfStudy,tldr,openAccessPdf'
    with httpx.Client() as client:
        r = client.get(url)

    json_string = r.text
    d = json.loads(json_string)

    paper_id = d['paperId']

    field_of_study = []
    if d['fieldsOfStudy'] is None:
        field_of_study = 'None'
    else:
        for i in d['fieldsOfStudy']:
            field_of_study.append(i)
    if d['tldr'] is None:
        tldr = 'None'
    else:
        tldr = d['tldr']
    
    if d['openAccessPdf'] is None:
        openaccess_pdf = 'None'
    else:
        openaccess_pdf = d['openAccessPdf']['url']


    #%% Constructing output dictionary
    output_dict = {
        # Paper Metadata
        'title':title,
        'authors':authors,
        #'abstract':abstract,
        #'scopus_id':scopus_id,
        'paperId':paper_id,
        'publication_name':pub_name,
        'publish_date':pub_date,
        'type':type,
        #'keywords':keywords,
        #'subject':subject,
        'fields_of_study':field_of_study,
        'institution_names':inst_names,
        'references':refs,
        'tldr':tldr,
        #'original_text':original_text,
        'openAccessPdf':openaccess_pdf,
        'URL_link':url_link 
    }
   
    return output_dict


async def async_paper_search(query, docs, chain):
    """
    Async version of paper search, run question for the document concurrently with other questions
    """
    out = await chain.arun(doc_text=docs, query=query)  # need to have await combined with chain.arun

    return out


async def langchain_paper_search(file_path):
    """
    Analyzes a pdf document defined by file_path and asks questions regarding the text
    using LLM's.
    The results are returned as unstructured text in a dictionary.
    """
    #%% Setup, defining framework of paper info extraction
    # Define language model to use
    llm = ChatOpenAI(model_name="gpt-3.5-turbo-16k", temperature=0)

    # Defining system and human prompts with variables
    system_template = "You are a world class research assistant who produces answers based on facts. \
                        You are tasked with reading the following publication text and answering questions based on the information: {doc_text}.\
                        You do not make up information that cannot be found in the text of the provided paper."

    system_message_prompt = SystemMessagePromptTemplate.from_template(system_template)  # providing the system prompt

    human_template = "{query}"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    chain = LLMChain(llm=llm, prompt=chat_prompt)


    #%% Extracting info from paper
    # Define the PDF document, load it in
    loader = PyPDFLoader(str(file_path))  # convert path to string to work with loader
    document = loader.load()

    # Define all the queries and corresponding schemas in a list
    queries_schemas_docs = [
        ("What are the experimental methods and techniques used by the authors? This can include ways that data was collected as well as ways the samples were synthesized.", document),
        ("What is the scientific question, challenge, or motivation that the authors are trying to address?", document),
        ("Provide a summary of the results and discussions in the paper. What results were obtained and what conclusions were reached?", document),
        ("Provide a summary of each figure described in the paper. Your response should be a one sentence summary of the figure description, \
         beginning with 'Fig. #  - description...', with each figure description separated by a comma. For example:'Fig. 1 - description..., Fig. 2 - description..., Fig. 3 - description...'", document),
        ("What future work or unanswered questions are mentioned by the authors?", document),
    ]

    tasks = []

    # Run the queries concurrently using asyncio.gather
    for query, docs in queries_schemas_docs:
        task = async_paper_search(query, docs, chain)
        tasks.append(task)

    summary = await asyncio.gather(*tasks)

    # Extracting individual elements from the summary
    methods, motive, results, figures, future = summary  #NOTE: output to variables in strings

    llm_output = {
        "motive": motive,
        "method": methods,
        "figures": figures,
        "results": results,
        "future": future
    }

    return llm_output


def jsonformer_structure(unstructured_dict):
    """
    Take in unstructured text contained in the dictionary output of langchain_paper_search
    and return structured json-ld using huggingface combined with jsonformer
    """
    structured_dict = 1
    #TODO: make code to do this

    return structured_dict


def pdfprocess(file_path): 
    results = pdfMetadata(file_path)
    print(results)
    #langchain = asyncio.run(langchain_paper_search(file_path))
    #print(langchain)
    return results
    

def pdfMetadata(file_path): 
    """
    This returns basic descriptive metadata for the PDF. 

    VARS: 
        Filepath: the path of the file you want to upload. 

    RETURNS: 
        metadata: This is the basic function of the Fitz library. 
        It scrapes the PDF for any embedded metadata. 
    """
    doc = fitz.open(file_path)
    metadata = doc.metadata
        
    #format, encryption, title, author, subject, keywords, creator, producer, creationDate, modDate, trapped
    
    secondary = read_single(file_path)
    
    #there's a chance that these never evaluate to false. Unsure why that is 
    if metadata['author'] == '' and secondary['author'] != '': 
        metadata['author'] == secondary['author']
        
    del secondary['author']

    if metadata['keywords'] == '' and secondary['keywords'] != '': 
        metadata['keywords'] == secondary['keywords']

    del secondary['keywords']
        
    metadata.update(secondary) 
    
   # if metadata['author'] == 'null': 
        #metadata['author'] == read.read_file(filepath)
    print(metadata)
    return metadata 


def results(paper_doi, pdf_path):

    #paper_doi = "10.1007/s13391-015-5352-y"
    #pdf_path = Path("s13391-015-5352-y-1.pdf")  # defining the location of the PDF file

    #%% Looking up info in databases
    api_lookup_results = paper_data_json_single(paper_doi)

    #%% Paper analysis using LangChain
    # Setting up the input and output folders
    # Load in API keys from .env file
    load_dotenv(find_dotenv())

    # Running summarization for a single document
    llm_output = asyncio.run(langchain_paper_search(pdf_path))

    # Constructing the final output
    final_output = api_lookup_results | llm_output


#%% Main, general case for testing
if __name__ == "__main__":
    print("Starting code run...")
    cwd = Path(__file__)
    pdf_folder = cwd.parents[1].joinpath('.test_pdf')  # path to the folder containing the pdf to test

    # File name of pdf in the .test_pdf folder for testing with code
    file_name = "1087792.pdf"
    pdf_file_path = pdf_folder.joinpath(file_name)

    llm_output = asyncio.run(langchain_paper_search(pdf_file_path))  # output of unstructured text in dictionary
