"""
Claude Code skills exported as Google Gemini function declarations.

Usage with google-genai (newer unified SDK):
    from google import genai
    from google.genai import types
    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="...",
        config=types.GenerateContentConfig(tools=GEMINI_TOOLS),
    )

Usage with google-generativeai (legacy SDK):
    import google.generativeai as genai
    model = genai.GenerativeModel("gemini-pro", tools=GEMINI_TOOLS)
"""

_SKILLS: list[dict] = [
    # ── Dev workflow ──────────────────────────────────────────────────────────
    {
        "name": "commit",
        "description": (
            "Stage changes, update CHANGELOG [Unreleased], commit, and push to a new branch ready for a PR."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Optional commit message override.",
                },
            },
        },
    },
    {
        "name": "release",
        "description": (
            "Cut a dlight-client release — bumps version, promotes CHANGELOG, "
            "commits, tags, and pushes to trigger automated PyPI publish."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "version": {
                    "type": "string",
                    "description": ("Version string to release (e.g. '1.7.0'). Omit to auto-bump the patch version."),
                },
            },
        },
    },
    {
        "name": "review_pr",
        "description": ("Fetch inline review comments on a GitHub PR, triage them, apply valid fixes, and push."),
        "parameters": {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "The pull request number to review and fix.",
                },
            },
            "required": ["pr_number"],
        },
    },
    {
        "name": "issue",
        "description": (
            "Fetch details of a GitHub issue, create a dedicated local branch, "
            "implement the changes, verify, and commit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "issue_number": {
                    "type": "integer",
                    "description": "The GitHub issue number to work on.",
                },
            },
            "required": ["issue_number"],
        },
    },
    {
        "name": "review",
        "description": "Review a pull request for correctness, style, and completeness.",
        "parameters": {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "GitHub PR number to review.",
                },
            },
        },
    },
    {
        "name": "code_review",
        "description": (
            "Review the current diff for correctness bugs and cleanups. "
            "Can post findings as inline PR comments or apply fixes directly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "effort": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "max", "ultra"],
                    "description": ("Review depth. 'ultra' runs a deep multi-agent cloud review."),
                },
                "fix": {
                    "type": "boolean",
                    "description": "Apply findings to the working tree after review.",
                },
                "comment": {
                    "type": "boolean",
                    "description": "Post findings as inline PR comments.",
                },
                "pr_number": {
                    "type": "integer",
                    "description": ("GitHub PR number to review. Omit to review the local diff."),
                },
            },
        },
    },
    {
        "name": "security_review",
        "description": "Perform a security-focused review of the current code changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Optional focus area for the security review.",
                },
            },
        },
    },
    {
        "name": "simplify",
        "description": (
            "Review changed code for reuse, simplification, and efficiency cleanups, "
            "then apply the fixes. Does not hunt for bugs — use code_review for that."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "verify",
        "description": (
            "Verify that a code change actually works by running the app and "
            "observing behavior. Use to confirm a fix works before pushing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": ("What to verify (e.g. 'the login flow works after the auth fix')."),
                },
            },
        },
    },
    {
        "name": "run",
        "description": (
            "Launch and drive the project app to observe a change. "
            "Use to run, start, or screenshot the app, or confirm a change works."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What aspect of the app to run or verify.",
                },
            },
        },
    },
    # ── Configuration & tooling ───────────────────────────────────────────────
    {
        "name": "update_config",
        "description": (
            "Configure the Claude Code harness via settings.json. "
            "Use for permissions, hooks, env vars, and automated behaviors."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": ("What to configure (e.g. 'allow npm commands', 'set DEBUG=true')."),
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "keybindings_help",
        "description": (
            "Customize keyboard shortcuts, rebind keys, add chord bindings, or modify ~/.claude/keybindings.json."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": ("What keybinding change to make (e.g. 'rebind ctrl+s', 'add a chord shortcut')."),
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "fewer_permission_prompts",
        "description": (
            "Scan transcripts for common read-only Bash and MCP tool calls, "
            "then add a prioritized allowlist to .claude/settings.json to reduce prompts."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "init",
        "description": "Initialize a new CLAUDE.md file with codebase documentation.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    # ── Scheduling & automation ───────────────────────────────────────────────
    {
        "name": "loop",
        "description": (
            "Run a prompt or slash command on a recurring interval. "
            "Use for polling, scheduled checks, or repeating a task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "interval": {
                    "type": "string",
                    "description": ("How often to run (e.g. '5m', '1h'). Omit for self-paced."),
                },
                "command": {
                    "type": "string",
                    "description": "The slash command or prompt to run each iteration.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "schedule",
        "description": (
            "Create, update, list, or run scheduled cloud agents that execute on a "
            "cron schedule. Also supports one-time scheduled runs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "update", "delete", "run"],
                    "description": "What to do with the schedule.",
                },
                "cron": {
                    "type": "string",
                    "description": (
                        "Cron expression (e.g. '0 9 * * 1-5') or natural language ('every weekday at 9am')."
                    ),
                },
                "command": {
                    "type": "string",
                    "description": "The task or slash command to schedule.",
                },
            },
        },
    },
    # ── Reference / docs ─────────────────────────────────────────────────────
    {
        "name": "claude_api",
        "description": (
            "Reference the Claude API / Anthropic SDK — model IDs, pricing, params, "
            "streaming, tool use, MCP, agents, caching, token counting, model migration."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": ("What to look up (e.g. 'latest model IDs', 'how to use streaming')."),
                },
            },
            "required": ["query"],
        },
    },
    # ── Cloudflare platform ───────────────────────────────────────────────────
    {
        "name": "cloudflare",
        "description": (
            "Cloudflare platform skill covering Workers, Pages, KV, D1, R2, AI, "
            "Vectorize, networking, security, and infrastructure-as-code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The Cloudflare development task to accomplish.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "agents_sdk",
        "description": (
            "Build AI agents on Cloudflare Workers using the Agents SDK. "
            "Covers stateful agents, durable workflows, WebSockets, MCP servers, and more."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The agent task to build or configure.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "durable_objects",
        "description": (
            "Create and review Cloudflare Durable Objects for stateful coordination "
            "(chat rooms, multiplayer, booking), RPC, SQLite, alarms, and WebSockets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The Durable Objects task to build or review.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "wrangler",
        "description": (
            "Cloudflare Workers CLI for deploying, developing, and managing Workers, "
            "KV, R2, D1, Vectorize, AI, Queues, Workflows, Pipelines, and Secrets Store."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The wrangler operation to perform.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "workers_best_practices",
        "description": (
            "Review and author Cloudflare Workers code against production best practices. "
            "Covers streaming, floating promises, global state, secrets, bindings, observability."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The Workers code to review or write.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "cloudflare_email_service",
        "description": (
            "Send and receive transactional emails with Cloudflare Email Service. "
            "Covers email sending, routing, SPF/DKIM/DMARC, and Workers integration."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The email service task to implement.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "sandbox_sdk",
        "description": (
            "Build sandboxed applications for secure code execution — AI code interpreters, "
            "CI/CD systems, interactive dev environments, or untrusted code execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The sandboxed execution task to build.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "web_perf",
        "description": (
            "Analyze web performance using Chrome DevTools. Measures Core Web Vitals "
            "(LCP, INP, CLS), identifies render-blocking resources, layout shifts, "
            "and caching issues."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the page to audit.",
                },
            },
            "required": ["url"],
        },
    },
]

# Ready to pass directly to either Gemini SDK:
#   google-genai  →  config=types.GenerateContentConfig(tools=GEMINI_TOOLS)
#   google-generativeai  →  genai.GenerativeModel(..., tools=GEMINI_TOOLS)
GEMINI_TOOLS = [{"function_declarations": _SKILLS}]
