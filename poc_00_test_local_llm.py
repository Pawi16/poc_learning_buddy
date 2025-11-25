from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM
from langchain_core.output_parsers import StrOutputParser


llm = OllamaLLM(model="llama3")

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert curriculum designer. Your output must be a concise, professional course outline."),
    ("user", "Create a course outline for a deep dive into the LangChain Expression Language (LCEL).")
])

output_parser = StrOutputParser()

chain = prompt | llm | output_parser

print("--- Generating Course Outline ---")
response = chain.invoke({})
print(response)