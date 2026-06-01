"""Conditional autoencoder on Marvin features (Phase 2, numpy)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .config import MODEL_DIR


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-9)


class MarvinAutoencoder:
    """Encoder: features -> K factors; decoder: factors -> features."""

    def __init__(self, n_features: int, n_factors: int, hidden: int = 16, seed: int = 42):
        rng = np.random.default_rng(seed)
        self.n_features = n_features
        self.n_factors = n_factors
        self.W1 = rng.normal(0, 0.1, (n_features, hidden))
        self.b1 = np.zeros(hidden)
        self.Wf = rng.normal(0, 0.1, (hidden, n_factors))
        self.bf = np.zeros(n_factors)
        self.Wd = rng.normal(0, 0.1, (n_factors, n_features))
        self.bd = np.zeros(n_features)

    def encode(self, X: np.ndarray) -> np.ndarray:
        H = _relu(X @ self.W1 + self.b1)
        return H @ self.Wf + self.bf

    def decode(self, F: np.ndarray) -> np.ndarray:
        return F @ self.Wd + self.bd

    def forward(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        F = self.encode(X)
        Xhat = self.decode(F)
        return F, Xhat

    def fit(self, X: np.ndarray, epochs: int = 80, lr: float = 0.02) -> list[float]:
        losses = []
        n = X.shape[0]
        for _ in range(epochs):
            F, Xhat = self.forward(X)
            err = Xhat - X
            loss = float(np.mean(err**2))
            losses.append(loss)
            dXhat = 2 * err / n
            dWd = F.T @ dXhat
            dbd = dXhat.sum(axis=0)
            dF = dXhat @ self.Wd.T
            dWf = (_relu(X @ self.W1 + self.b1)).T @ dF
            dbf = dF.sum(axis=0)
            dH = dF @ self.Wf.T
            dH *= (X @ self.W1 + self.b1 > 0).astype(float)
            dW1 = X.T @ dH
            db1 = dH.sum(axis=0)
            self.Wd -= lr * dWd
            self.bd -= lr * dbd
            self.Wf -= lr * dWf
            self.bf -= lr * dbf
            self.W1 -= lr * dW1
            self.b1 -= lr * db1
        return losses

    def to_dict(self) -> dict:
        return {
            "n_features": self.n_features,
            "n_factors": self.n_factors,
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "Wf": self.Wf.tolist(),
            "bf": self.bf.tolist(),
            "Wd": self.Wd.tolist(),
            "bd": self.bd.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MarvinAutoencoder":
        m = cls(d["n_features"], d["n_factors"])
        m.W1 = np.array(d["W1"])
        m.b1 = np.array(d["b1"])
        m.Wf = np.array(d["Wf"])
        m.bf = np.array(d["bf"])
        m.Wd = np.array(d["Wd"])
        m.bd = np.array(d["bd"])
        return m


def standardize(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = X.mean(axis=0)
    sig = X.std(axis=0) + 1e-6
    return (X - mu) / sig, mu, sig


def train_encoder(
    tickers: list[dict],
    n_factors: int = 5,
    epochs: int = 80,
    lr: float = 0.02,
    seed: int = 42,
) -> tuple[MarvinAutoencoder, dict[str, list[float]], dict]:
    names = tickers[0]["feature_names"]
    X = np.array([t["feature_vector"] for t in tickers], dtype=float)
    Xn, mu, sig = standardize(X)
    model = MarvinAutoencoder(Xn.shape[1], n_factors, seed=seed)
    losses = model.fit(Xn, epochs=epochs, lr=lr)
    F = model.encode(Xn)
    latent = {tickers[i]["ticker"]: F[i].tolist() for i in range(len(tickers))}
    factor_labels = [f"factor_{i+1}" for i in range(n_factors)]
    meta = {
        "feature_names": names,
        "mu": mu.tolist(),
        "sig": sig.tolist(),
        "factor_labels": factor_labels,
        "final_loss": losses[-1] if losses else None,
        "epochs": epochs,
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "encoder.json").write_text(
        json.dumps({"model": model.to_dict(), "meta": meta}, indent=2) + "\n",
        encoding="utf-8",
    )
    return model, latent, meta


def load_encoder() -> tuple[MarvinAutoencoder | None, dict]:
    path = MODEL_DIR / "encoder.json"
    if not path.exists():
        return None, {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return MarvinAutoencoder.from_dict(data["model"]), data.get("meta") or {}
