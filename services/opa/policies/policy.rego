package em_agent

default decision = {"allow": true, "action": "nudge"}

# Example blocks: tune as needed
decision = {"allow": false, "action": "block", "reason": "wip limit exceeded"} {
  input.kind == "wip_limit_exceeded"
}

decision = {"allow": true, "action": "nudge", "reason": "stale PR"} {
  input.kind == "stale_pr"
}


