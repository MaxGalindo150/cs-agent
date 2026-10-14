# Skills

Domain policies the agent loads **only when a message calls for them**
(progressive disclosure — `src/agent/memory/procedural/loader.py`). One
directory per audience, so a policy for end customers never reaches an aliado
and the reverse:

```
skills/
├── consumer/<skill-name>/SKILL.md   end customers
└── merchant/<skill-name>/SKILL.md   aliados (merchant employees)
```

A `SKILL.md` is the Anthropic Agent Skills format: YAML frontmatter with
`name` and `description` — the description is also the trigger, matched
against the user's message — then the policy as Markdown.

Keep each skill short (30–60 human-written lines) and write one only where the
agent actually gets something wrong without it. Always-on behavior belongs in
the soul (`../prompts/souls/`), not here.
