import re

with open('dct/cli/main.py', 'r') as f:
    content = f.read()

# Add add-openrouter to help text
help_old = """  dct add <host> <port> [alias] [note]    register a server
  dct remove <alias|#>                    remove a server"""

help_new = """  dct add <host> <port> [alias] [note]    register a server
  dct add-openrouter <key> [alias]        register OpenRouter
  dct remove <alias|#>                    remove a server"""

content = content.replace(help_old, help_new)

# Add add-openrouter parser
parser_old = """    # add
    pa = sub.add_parser("add", help="register a server")
    pa.add_argument("host")
    pa.add_argument("port", type=int)
    pa.add_argument("alias", nargs="?", default="")
    pa.add_argument("note", nargs="?", default="")

    # remove"""

parser_new = """    # add
    pa = sub.add_parser("add", help="register a server")
    pa.add_argument("host")
    pa.add_argument("port", type=int)
    pa.add_argument("alias", nargs="?", default="")
    pa.add_argument("note", nargs="?", default="")

    # add-openrouter
    po = sub.add_parser("add-openrouter", help="register OpenRouter")
    po.add_argument("key", help="OpenRouter API Key")
    po.add_argument("alias", nargs="?", default="openrouter")

    # remove"""

content = content.replace(parser_old, parser_new)

# Add add-openrouter logic
logic_old = """        else:
            con.print(f"[{C['err']}]offline[/{C['err']}]")
            warn(f"added as {srv.alias} but currently unreachable")
        return

    if args.cmd == "remove":"""

logic_new = """        else:
            con.print(f"[{C['err']}]offline[/{C['err']}]")
            warn(f"added as {srv.alias} but currently unreachable")
        return

    if args.cmd == "add-openrouter":
        srv = registry.add("openrouter.ai", 443, args.alias, "OpenRouter API", provider="openrouter", api_key=args.key)
        con.print(f"  [{C['dim']}]probing…[/{C['dim']}]", end=" ")
        res = probe_server(srv)
        registry.save()
        if res["ok"]:
            con.print(f"[{C['ok']}]online[/{C['ok']}]")
            ok(f"added: {srv.alias}  ({len(srv.models)} models available)")
        else:
            con.print(f"[{C['err']}]offline[/{C['err']}]")
            warn(f"added {srv.alias} but API key might be invalid")
        return

    if args.cmd == "remove":"""

content = content.replace(logic_old, logic_new)

# Fix imports
import_old = "from dct.core.ollama import list_models, pull_stream, delete_model"
import_new = "from dct.core.client import list_models, pull_stream, delete_model"

content = content.replace(import_old, import_new)

with open('dct/cli/main.py', 'w') as f:
    f.write(content)
