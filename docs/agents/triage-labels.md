# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `question`           | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the "Label in our tracker" column to match whatever vocabulary you actually use.

## Which labels exist

`question` and `wontfix` already exist in this repo. `question` is GitHub's default "Further information is requested" label, so it stands in for `needs-info` instead of adding a duplicate.

`needs-triage`, `ready-for-agent`, and `ready-for-human` do not exist yet. Before `/triage` applies them, a maintainer creates them once:

```bash
gh label create needs-triage --color fbca04 --description "Maintainer needs to evaluate this issue"
gh label create ready-for-agent --color 0e8a16 --description "Fully specified, ready for an AFK agent"
gh label create ready-for-human --color 1d76db --description "Requires human implementation"
```

Until then, a skill that needs one of those three labels stops and says the label is missing. It does not create a label on its own and does not substitute another one.
