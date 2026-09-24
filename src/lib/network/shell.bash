# Bash integration: read the persistent switch at each prompt, never start services.
# Source this file; Python subprocesses cannot change their parent shell.
unset -f proxy_on proxy_off _autodl_proxy_env 2>/dev/null
_autodl_proxy_refresh() {
    local previous_status=$? proxy_exports
    if proxy_exports="$(command autodl proxy env)"; then
        eval "$proxy_exports"
    fi
    return "$previous_status"
}
_autodl_proxy_hook_present=
for _autodl_proxy_hook in "${PROMPT_COMMAND[@]}"; do
    [[ $_autodl_proxy_hook == _autodl_proxy_refresh ]] && _autodl_proxy_hook_present=1
done
if [[ -z $_autodl_proxy_hook_present ]]; then
    if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == 'declare -a '* ]]; then
        PROMPT_COMMAND+=(_autodl_proxy_refresh)
    else
        PROMPT_COMMAND=("${PROMPT_COMMAND:-:}" _autodl_proxy_refresh)
    fi
fi
unset _autodl_proxy_hook _autodl_proxy_hook_present
_autodl_proxy_refresh
