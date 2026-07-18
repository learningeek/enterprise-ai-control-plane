# Behavior model

Define *how* the simulated enterprise behaves before writing any generator code. This is what makes
generated data feel real instead of uniformly random.

Example behavior rules (adjust/extend as needed, these are starting assumptions):
- Engineering uses AI roughly 8x more than HR.
- Finance operates under stricter governance (more blocked/flagged events).
- Legal has fewer requests but higher average context length (long documents).
- Customer Support has high request volume with short prompts.

The generator (`simulation/`) should implement these rules rather than generating uniform random data.
