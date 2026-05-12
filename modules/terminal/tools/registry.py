"""Tool definitions for AI models."""

POWERSHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_powershell",
        "description": (
            "Run a PowerShell command on the user's Windows PC and return its real "
            "output. Use this for ANY question about the system: installed software, "
            "versions, files, folders, processes, hardware, environment variables, "
            "network, dates, or to perform an action. Never guess — always run a "
            "command and answer only from its real output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The PowerShell command to execute.",
                }
            },
            "required": ["command"],
        },
    },
}
