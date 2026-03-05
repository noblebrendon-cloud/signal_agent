"""Curated lexicons for Interaction Signals feature extraction."""
from __future__ import annotations

CERTAINTY_MARKERS: frozenset[str] = frozenset([
    "definitely", "certainly", "absolutely", "clearly", "obviously",
    "undoubtedly", "always", "never", "must", "will", "guaranteed",
    "impossible", "certain", "proven", "fact", "100", "without doubt",
    "unquestionably", "evidently", "plainly", "conclusively", "assured",
])

HEDGE_MARKERS: frozenset[str] = frozenset([
    "perhaps", "maybe", "might", "could", "possibly", "presumably",
    "approximately", "roughly", "likely", "unlikely", "seems", "appears",
    "suggest", "indicate", "tend", "usually", "often", "sometimes",
    "generally", "fairly", "somewhat", "rather", "partially", "arguably",
    "conceivably", "potentially", "suppose", "assume", "believe", "think",
])

CAUSAL_MARKERS: frozenset[str] = frozenset([
    "because", "therefore", "thus", "hence", "since", "causes",
    "results", "implies", "consequently", "owing", "follows", "given",
    "provided", "assuming", "leads", "produces", "generates", "entails",
])

INTEGRATION_MARKERS: frozenset[str] = frozenset([
    "furthermore", "moreover", "additionally", "besides", "however",
    "nevertheless", "nonetheless", "whereas", "conversely", "similarly",
    "likewise", "contrast", "building", "extending", "connecting",
    "synthesis", "synthesize", "integrate", "combining", "together",
])

EXTRACTION_MARKERS: frozenset[str] = frozenset([
    "give me", "tell me your", "send me", "share with me", "connect with",
    "book a call", "schedule", "dm me", "reach out", "your email",
    "contact me", "sign up", "register", "subscribe", "follow me",
    "click here", "my offer", "my service", "my course", "my program",
])

AUTHORITY_MARKERS: frozenset[str] = frozenset([
    "studies show", "research shows", "experts say", "scientists found",
    "according to", "data shows", "evidence suggests", "the literature",
    "peer reviewed", "meta analysis", "systematic review", "published",
    "cited", "referenced", "authority", "credentialed", "certified",
    "accredited", "endorsed", "recognized",
])

ADVERSARIAL_MARKERS: frozenset[str] = frozenset([
    "ridiculous", "absurd", "naive", "stupid", "wrong", "ignorant",
    "nonsense", "garbage", "trash", "delusional", "clueless",
    "incompetent", "dishonest", "liar", "fraud", "pathetic", "laughable",
])

PROMO_MARKERS: frozenset[str] = frozenset([
    "i help", "i work with", "my clients", "dm me", "book a call",
    "schedule a call", "my program", "my course", "my service",
    "link in bio", "my offer", "free consultation", "limited spots",
    "join my", "enroll", "special offer", "exclusive access",
])

CHALLENGE_MARKERS: frozenset[str] = frozenset([
    "prove", "source", "citation", "demonstrate", "show me",
    "edge case", "what if", "fails", "counterexample",
    "how do you know", "under what conditions", "can you show",
    "what evidence", "why should", "justify",
])

REPAIR_MARKERS: frozenset[str] = frozenset([
    "fair point", "you are right", "good point", "i agree",
    "let me clarify", "to clarify", "what i meant", "let me rephrase",
    "to be more precise", "i should have", "correction", "actually",
    "i misspoke", "let me correct", "apologies", "my mistake",
])

CONTACT_PULL_MARKERS: frozenset[str] = frozenset([
    "dm me", "message me", "email me", "reach out", "contact me",
    "book a call", "schedule", "link in bio", "comment below",
    "follow for more", "subscribe",
])

SELF_REF_TOKENS: frozenset[str] = frozenset([
    "i", "my", "me", "myself", "mine", "i'm", "i've", "i'll",
])
