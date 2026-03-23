import json
from typing import List, Dict, Any, Optional

from langchain_openai import AzureChatOpenAI
from langchain.prompts import ChatPromptTemplate


class BetterChatbot:
    # ======================================================
    # INIT
    # ======================================================

    def __init__(
        self,
        azure_api_key: str,
        azure_endpoint: str,
        azure_api_version: str,
        deployment_name: str,
        course_text: str,
        catalog_path: str,
        temperature: float = 0.2,
        max_context_chars: int = 5000,
    ):
        # ----- Config Azure (lazy init) -----
        self._azure_cfg = {
            "api_key": azure_api_key,
            "azure_endpoint": azure_endpoint,
            "api_version": azure_api_version,
            "deployment_name": deployment_name,
            "temperature": temperature,
        }
        self.llm = None  # só criaremos quando for realmente usar (chat livre)

        # ----- Prompt / Chain -----
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "Você é um orientador vocacional claro, objetivo e confiável.\n"
                        "Use EXCLUSIVAMENTE o conteúdo fornecido em CONTEXTO quando ele existir.\n\n"
                        "=== CONTEXTO ===\n{context}\n=== FIM DO CONTEXTO ==="
                    ),
                ),
                ("human", "{input}"),
            ]
        )
        # chain será criado no primeiro uso do LLM
        self._chain = None

        # ----- Catálogo -----
        try:
            with open(catalog_path, encoding="utf-8") as f:
                self.cursos: List[Dict[str, Any]] = json.load(f)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Catálogo não encontrado em '{catalog_path}'. Verifique o caminho."
            ) from e
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Catálogo '{catalog_path}' não é um JSON válido: {e}"
            ) from e

        # ----- RAG -----
        self._custom_docs: List[Dict[str, Any]] = []
        self._max_context_chars = max_context_chars

        # ----- RIASEC -----
        self.riasec = {
            "R": "Realista (R)",
            "I": "Investigativo (I)",
            "A": "Artístico (A)",
            "S": "Social (S)",
            "E": "Empreendedor (E)",
        }

        self.perguntas = [
            ("R", "Prefiro atividades práticas e concretas."),
            ("R", "Gosto de trabalhar com máquinas ou objetos físicos."),
            ("R", "Trabalhos muito teóricos me desmotivam."),
            ("I", "Gosto de investigar problemas e analisar dados."),
            ("I", "Pesquisar para entender melhor me motiva."),
            ("I", "Prefiro entender bem antes de agir."),
            ("A", "Valorizo criatividade e expressão pessoal."),
            ("A", "Ambientes muito rígidos limitam meu desempenho."),
            ("A", "Gosto de atividades ligadas à arte ou criação."),
            ("S", "Gosto de ajudar e orientar pessoas."),
            ("S", "Tenho paciência para ensinar ou apoiar."),
            ("S", "Busco impacto humano ou social."),
            ("E", "Gosto de liderar ou influenciar decisões."),
            ("E", "Assumir riscos calculados me atrai."),
            ("E", "Tenho interesse por negócios e resultados."),
        ]

        self.reset()

    # ======================================================
    # Helpers LLM
    # ======================================================

    def _ensure_llm(self):
        """Inicializa LLM e chain no primeiro uso (lazy)."""
        if self.llm is None:
            cfg = self._azure_cfg
            missing = [k for k, v in cfg.items() if k != "temperature" and not v]
            if missing:
                # Não impede uploads de PDF, apenas o chat livre
                raise RuntimeError(
                    f"Configuração do Azure OpenAI ausente: {', '.join(missing)}. "
                    "Defina as variáveis de ambiente ou o .env antes de usar o chat."
                )

            self.llm = AzureChatOpenAI(
                api_key=cfg["api_key"],
                azure_endpoint=cfg["azure_endpoint"],
                api_version=cfg["api_version"],
                deployment_name=cfg["deployment_name"],
                temperature=cfg["temperature"],
            )
            self._chain = self.prompt | self.llm

    # ======================================================
    # ESTADO
    # ======================================================

    def reset(self) -> Dict[str, Any]:
        self.questionario_ativo = False
        self.pergunta_atual = 0
        self.respostas: List[int] = []
        return {
            "text": "Bem-vindo. Digite /questionario para iniciar o teste vocacional."
        }

    # ======================================================
    # RAG — PDFs
    # ======================================================

    def add_custom_document(self, text: str, metadata: Optional[Dict[str, Any]] = None):
        if text and text.strip():
            self._custom_docs.append({
                "text": text.strip(),
                "metadata": metadata or {}
            })

    def clear_custom_documents(self) -> int:
        n = len(self._custom_docs)
        self._custom_docs.clear()
        return n

    def count_custom_documents(self) -> int:
        return len(self._custom_docs)

    def _build_context(self) -> str:
        if not self._custom_docs:
            return ""

        parts = []
        size = 0
        for d in self._custom_docs:
            chunk = d["text"]
            remaining = self._max_context_chars - size
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            parts.append(chunk)
            size += len(chunk)

        return "\n\n---\n\n".join(parts)

    # ======================================================
    # PERFIL
    # ======================================================

    def _normalizar_tag(self, tag: str) -> Optional[str]:
        if not tag:
            return None
        t = tag.lower().strip()
        for k, v in self.riasec.items():
            if t == k.lower() or t == v.lower():
                return v
        return None

    def _perfil(self) -> Dict[str, int]:
        raw = {k: 0 for k in self.riasec}
        for (f, _), r in zip(self.perguntas, self.respostas):
            raw[f] += r
        return {self.riasec[k]: v for k, v in raw.items()}

    def _perfil_texto(self, perfil: Dict[str, int]) -> str:
        top = sorted(perfil.items(), key=lambda x: x[1], reverse=True)[:2]
        return (
            f"Seu perfil mostra predominância em {top[0][0]} "
            f"com forte presença de {top[1][0]}."
        )

    def _rank(self, perfil: Dict[str, int]) -> List[Dict[str, Any]]:
        ranked = []
        max_possible = 15.0
        perfil_norm = {k: v / max_possible for k, v in perfil.items()}

        for c in self.cursos:
            fatores = []
            for t in c.get("tags", []):
                f = self._normalizar_tag(t)
                if f:
                    fatores.append(f)
            if not fatores:
                continue

            similarity = sum(perfil_norm[f] for f in fatores) / len(fatores)

            for f, v in perfil_norm.items():
                if v >= 0.7 and f not in fatores:
                    similarity *= 0.75

            cc = dict(c)
            cc["score"] = round(similarity * 10, 2)
            ranked.append(cc)

        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    # ======================================================
    # CHAT
    # ======================================================

    def chat(self, message: str) -> Dict[str, Any]:
        msg = message.strip()

        # Reset explícito
        if msg == "/reset":
            return self.reset()

        # Início do questionário
        if msg == "/questionario":
            self.questionario_ativo = True
            self.pergunta_atual = 0
            self.respostas.clear()
            return {
                "text": (
                    f"Pergunta 1 de 15. "
                    f"{self.perguntas[0][1]} "
                    "Responda com um número de 1 a 5."
                )
            }

        # Fluxo do questionário
        if self.questionario_ativo:
            try:
                v = int(msg)
                if not 1 <= v <= 5:
                    raise ValueError

                self.respostas.append(v)
                self.pergunta_atual += 1

                if self.pergunta_atual < len(self.perguntas):
                    return {
                        "text": (
                            f"Pergunta {self.pergunta_atual + 1} de 15. "
                            f"{self.perguntas[self.pergunta_atual][1]} "
                            "Responda com um número de 1 a 5."
                        )
                    }

                if len(set(self.respostas)) == 1:
                    self.questionario_ativo = True
                    self.pergunta_atual = 0
                    self.respostas.clear()

                    return {
                        "text": (
                            "Atenção. Suas respostas ficaram todas iguais.\n\n"
                            "Para que o teste funcione corretamente, é necessário "
                            "diferenciar o que você gosta muito, gosta pouco "
                            "e o que não gosta.\n\n"
                            "Use toda a escala:\n"
                            "1 = Não gosto\n"
                            "3 = Depende / Indiferente\n"
                            "5 = Gosto muito\n\n"
                            "Vamos tentar novamente.\n\n"
                            f"Pergunta 1 de 15. {self.perguntas[0][1]} "
                            "Responda com um número de 1 a 5."
                        )
                    }

                # Finaliza normalmente
                self.questionario_ativo = False
                perfil = self._perfil()

                return {
                    "text": "Questionário finalizado com sucesso.",
                    "perfil_texto": self._perfil_texto(perfil),
                    "scores": perfil,
                    "recommendations": self._rank(perfil)[:6],
                }

            except ValueError:
                return {
                    "text": "Responda apenas com um número inteiro entre 1 e 5."
                }

        # ---------- Chat livre com RAG ----------
        context = self._build_context()

        # Inicializa LLM/chain sob demanda
        self._ensure_llm()

        resp = self._chain.invoke({
            "input": message,
            "context": context
        })
        resposta = resp.content if hasattr(resp, "content") else str(resp)

        return {"text": resposta}