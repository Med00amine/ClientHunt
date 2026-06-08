"""Skill lexicon: canonical skill -> regex aliases. Matching is on word boundaries."""
import re

MY_SKILLS = {
    "python", "fastapi", "rest api", "pytorch", "machine learning", "llm", "rag", "aws", "docker",
    "ci/cd", "testing", "document processing", "workflow automation", "api integration",
    "postgresql", "nlp", "react", "typescript",
}

LEXICON: dict[str, list[str]] = {
    "python": [r"python"],
    "fastapi": [r"fast\s?api"],
    "rest api": [r"rest(ful)?\s+apis?", r"apis?\s+development", r"backend\s+apis?"],
    "pytorch": [r"pytorch", r"torch"],
    "machine learning": [r"machine[\s-]learning", r"\bml\b", r"deep[\s-]learning", r"scikit-?learn", r"data\s+scien"],
    "llm": [r"\bllms?\b", r"large\s+language\s+models?", r"openai", r"anthropic", r"gpt-?\d", r"claude",
            r"langchain", r"generative\s+ai", r"\bgen\s?ai\b", r"prompt\s+engineering"],
    "rag": [r"\brag\b", r"retrieval[\s-]augmented", r"vector\s+(db|database|store|search)", r"embeddings?",
            r"pinecone", r"qdrant", r"pgvector", r"chroma"],
    "nlp": [r"\bnlp\b", r"natural\s+language\s+processing"],
    "aws": [r"\baws\b", r"amazon\s+web\s+services", r"\bec2\b", r"\blambda\b", r"\bs3\b", r"bedrock", r"sagemaker",
            r"cloudformation", r"\becs\b|\beks\b"],
    "docker": [r"docker", r"container(s|ization|ised|ized)?", r"kubernetes|\bk8s\b"],
    "ci/cd": [r"ci/?cd", r"github\s+actions", r"gitlab\s+ci", r"jenkins", r"continuous\s+(integration|delivery|deployment)"],
    "testing": [r"pytest", r"unit\s+tests?", r"test[\s-]driven", r"automated\s+testing"],
    "document processing": [r"document\s+(processing|parsing|extraction|ai)", r"\bocr\b", r"pdf\s+(parsing|extraction|processing)",
                            r"data\s+extraction", r"intelligent\s+document"],
    "workflow automation": [r"workflow\s+automation", r"\bautomation\b", r"\bzapier\b", r"\bn8n\b", r"\bmake\.com\b", r"\brpa\b"],
    "api integration": [r"api\s+integrations?", r"integrat(e|ing|ions?)\s+(with\s+)?(third[\s-]party\s+)?apis?",
                        r"\bwebhooks?\b", r"third[\s-]party\s+integrations?"],
    "postgresql": [r"postgres(ql)?"],
    "react": [r"\breact(\.js|js)?\b"],
    "typescript": [r"typescript"],
    # not mine: tracked so the app can report missing requirements honestly
    "java": [r"\bjava\b"],
    "javascript": [r"\bjavascript\b|\bnode(\.js|js)?\b"],
    "php": [r"\bphp\b|\blaravel\b|\bwordpress\b"],
    "c#/.net": [r"\bc#|\.net\b|dotnet"],
    "ruby": [r"\bruby\b|\brails\b"],
    "go": [r"\bgolang\b|\bgo\s+developer\b"],
    "rust": [r"\brust\b"],
    "c++": [r"\bc\+\+"],
    "mobile": [r"\bios\b|\bandroid\b|react\s+native|\bflutter\b|\bswift\b|\bkotlin\b"],
    "azure": [r"\bazure\b"],
    "gcp": [r"\bgcp\b|google\s+cloud"],
    "terraform": [r"terraform"],
    "sap/salesforce": [r"\bsap\b|salesforce"],
    "devops": [r"\bdevops\b|\bsre\b"],
}

_COMPILED = {k: [re.compile(p, re.I) for p in pats] for k, pats in LEXICON.items()}


def extract_skills(*texts: str) -> list[str]:
    blob = "\n".join(t for t in texts if t)
    return [k for k, pats in _COMPILED.items() if any(p.search(blob) for p in pats)]
