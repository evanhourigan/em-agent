package em_agent

default decision = {"allow": true, "action": "nudge"}

# Example blocks: tune as needed (Rego v1 syntax uses 'if')
decision = {"allow": false, "action": "block", "reason": "wip limit exceeded"} if {
  input.kind == "wip_limit_exceeded"
}

decision = {"allow": true, "action": "nudge", "reason": "stale PR"} if {
  input.kind == "stale_pr"
}

