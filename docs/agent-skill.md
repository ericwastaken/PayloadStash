# Install the PayloadStash agent skill

Give a compatible coding agent PayloadStash-specific instructions for creating and updating HTTP and AMQP configuration files. The skill covers the current schema, value operators, per-request `URLRoot` overrides, captures, expectations, examples, and CLI commands.

[View `SKILL.md` on GitHub](https://github.com/ericwastaken/PayloadStash/blob/main/SKILL.md){ .md-button .md-button--primary }
[Download the raw skill](https://raw.githubusercontent.com/ericwastaken/PayloadStash/main/SKILL.md){ .md-button }

## Install for a project

Agent hosts discover skills from different directories. For hosts that support the shared `.agents/skills` project convention, run this from your project root:

```bash
mkdir -p .agents/skills/payloadstash
curl --fail --location \
  https://raw.githubusercontent.com/ericwastaken/PayloadStash/main/SKILL.md \
  --output .agents/skills/payloadstash/SKILL.md
```

This makes the skill available only while the agent works in that project. Commit the downloaded file if your team wants everyone to use the same reviewed revision.

## Install for your user account

For an agent host that reads user-level skills from `~/.agents/skills`, install it once for all your projects:

```bash
mkdir -p ~/.agents/skills/payloadstash
curl --fail --location \
  https://raw.githubusercontent.com/ericwastaken/PayloadStash/main/SKILL.md \
  --output ~/.agents/skills/payloadstash/SKILL.md
```

!!! note "Use your agent's configured skills directory"
    Some hosts use a product-specific directory instead of `.agents/skills`. In that case, replace the directory in the command with the skills directory documented by your agent host, while preserving the `payloadstash/SKILL.md` layout.

Restart the agent session or ask the host to reload skills after installation. Then make a request such as:

> Use the PayloadStash skill to create a configuration that checks two API hosts, captures an ID from the first response, and verifies it in the second.

## Update the skill

Run the same download command again to replace the installed copy with the current `main` version. To pin an auditable revision, replace `main` in the raw URL with a release tag or commit SHA.

The installed file should begin with skill metadata similar to:

```yaml
---
name: payloadstash
description: Create, edit, and validate PayloadStash YAML configurations for HTTP and AMQP workflows.
---
```

## Remove the skill

Delete only its directory from the applicable skills root:

```bash
rm -rf .agents/skills/payloadstash
```

For a user-level installation, use `~/.agents/skills/payloadstash` instead. Removing the skill does not uninstall the PayloadStash CLI.