# Bash completion for thc toolkit
# Save this file and source it in ~/.bashrc

_thc_complete() {
    local cur prev commands opts

    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    commands="counties route viewcsv convertHMDB docs"

    case "${prev}" in
        counties)
            opts="--input --output --county --merge --stats --summary-json --simple"
            COMPREPLY=( $(compgen -W "${opts}" -- "$cur") )
            return
            ;;
        route)
            opts="--track --data --radius --unmapped --csv --simple --geojson --kml --openmap"
            COMPREPLY=( $(compgen -W "${opts}" -- "$cur") )
            return
            ;;
        viewcsv)
            opts="--raw --head --tail --search --interactive"
            COMPREPLY=( $(compgen -W "${opts}" -- "$cur") )
            return
            ;;
        convertHMDB)
            opts="--input --output"
            COMPREPLY=( $(compgen -W "${opts}" -- "$cur") )
            return
            ;;
        docs)
            opts="counties route"
            COMPREPLY=( $(compgen -W "${opts}" -- "$cur") )
            return
            ;;
    esac

    # Top-level commands
    COMPREPLY=( $(compgen -W "${commands}" -- "$cur") )
}

complete -F _thc_complete thc
