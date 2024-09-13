import numpy as np
import shap
from sentence_transformers import SentenceTransformer
from langchain_community.embeddings import GPT4AllEmbeddings
from sklearn.metrics.pairwise import cosine_similarity


class SimilarityExplainer:
    def __init__(self, search_index):
        #self.model = SentenceTransformer(model_name)

        if search_index.use_hf_model == True:
            self.model_type = 'sentence_transformers' 
            self.model = SentenceTransformer(search_index.embedding_model)
            self.encoding_method = self.encode_sbert
        else: 
            self.model_type = 'gpt4all'
            self.model = GPT4AllEmbeddings(model_name=search_index.embedding_model)
            self.encoding_method = self.encode_gpt4all
        # Todo: Extend with other models here

    def encode_sbert(self, text):
        return self.model.encode([text])[0]

    def encode_gpt4all(self, text):
        return np.array(self.model.embed_query(text))
    
    def similarity(self, emb1, emb2):
        return cosine_similarity([emb1], [emb2])[0][0]
    
    def explain_similarity(self, query, document, n_samples=100):
        tokens = document.split()
        query_emb = self.encoding_method(query)
        token_embs = np.array([self.encoding_method(token) for token in tokens])
        
        def f(x):
            x = x.astype(bool)
            # Use vectorized operations for speed
            masked_embeddings = (x[:, :, np.newaxis] * token_embs[np.newaxis, :, :]).sum(axis=1)
            norms = np.linalg.norm(masked_embeddings, axis=1, keepdims=True)
            masked_embeddings = np.where(norms != 0, masked_embeddings / norms, 0)
            similarities = cosine_similarity(masked_embeddings, [query_emb]).flatten()
            return similarities
        
        # Create a background dataset
        background = np.eye(len(tokens))
        
        explainer = shap.KernelExplainer(f, background)
        shap_values = explainer.shap_values(np.ones((1, len(tokens))), nsamples=n_samples)
        
        # Debug information
        # print(f"Base similarity: {self.similarity(query_emb, token_embs.sum(axis=0)):.4f}")
        # background_sims = f(background)

        # print(f"Min similarity in samples: {background_sims.min():.4f}")
        # print(f"Max similarity in samples: {background_sims.max():.4f}")
        # print(f"SHAP expected value: {explainer.expected_value:.4f}")
        
        token_importance = list(zip(tokens, shap_values[0]))
        return [x for x in sorted(token_importance, key=lambda x: abs(x[1]), reverse=True) if x[1] > 0][:5]
