from mimetypes import knownfiles

from tree_sitter import Language, Parser
from langchain.tools import tool
import os, json
import glob


Language.build_library(
    'build/my-languages.so',
    ['tree-sitter-cpp']
)

CPP_LANGUAGE = Language('build/my-languages.so','cpp')

parser = Parser()
parser.set_language(CPP_LANGUAGE)

class CppCodeExtractor:
    def __init__(self, project_path):
        self.project_path = project_path
        self.symbol_map = {}

        # query định nghĩa
        self.def_query = CPP_LANGUAGE.query("""
            
        
            ;
            (function_definition
                declarator: (function_declarator
                    declarator: (identifier) @func.name                   
                )
            ) @func.def
            
            (function_definition
                declarator: (function_declarator
                    declarator: (qualified_identifier) @func.qualified_name
                )
            ) @func.def
    
            (class_specifier
                name: (type_identifier) @class.name
            ) @class.def
            
    
            (struct_specifier
                name: (type_identifier) @struct.name
            ) @struct.def
            
            
            (preproc_def name: (identifier) @macro.name) @macro.def
            (preproc_include path: (_) @include.path) @include.def
            
            (declaration declarator: (identifier) @var.name) @var.def
            (declaration declarator: (init_declarator declarator: (identifier) @var.name)) @var.def
            (declaration declarator: (array_declarator declarator: (identifier) @var.name)) @var.def
            """
        )

        # query cho phụ thuộc
        self.dep_query = CPP_LANGUAGE.query("""
            (parameter_declaration 
                type: (type_identifier) @type.name
            )
            (template_type 
                (type_identifier) @type.name
            )
            
            (call_expression function: (identifier) @call.name)
            (call_expression function: (field_expression field: (field_identifier) @method.name))            
            (type_identifier) @type.name
            (identifier) @ident.name
        """
        )

    def index_project(self):
        files = glob.glob(os.path.join(self.project_path, "**", "*.cpp"), recursive=True) + \
                glob.glob(os.path.join(self.project_path, "**", "*.h"), recursive=True)

        for file_path in files:
            with open(file_path, 'rb') as f:
                content = f.read()
            tree = parser.parse(content)
            captures = self.def_query.captures(tree.root_node)

            for node, tag in captures:
                name = None
                if tag == "include.path":
                    path_text = content[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
                    if path_text.startswith('"'):
                        continue
                    elif path_text.startswith('<'):
                        name = path_text.strip('<>')

                elif tag in ["func.name", "class.name", "struct.name", "macro.name", "var.name"]:
                    name = content[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
                elif tag == "func.qualified_name":
                    name = content[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

                if name:
                    def_node = node

                    valid_types = ['function_definition', 'class_specifier', 'struct_specifier', 'declaration', 'preproc_def', 'preproc_include']

                    while def_node.parent:
                        # filter cho biến toàn cục
                        if def_node.type in valid_types:
                            if def_node.type == 'declaration':
                                if def_node.parent.type not in ['translation_unit', 'namespace_definition']:
                                    def_node = None
                                    break
                            break
                        def_node = def_node.parent

                    if def_node:
                        code_block = content[def_node.start_byte:def_node.end_byte].decode('utf-8')

                        should_update = True

                        if name in self.symbol_map:
                            old_code = self.symbol_map[name]['code']

                            if len(code_block) < len(old_code):
                                should_update = False
                        if should_update:
                            self.symbol_map[name] = {
                                'code': code_block,
                                'file': file_path,
                                'type': def_node.type,
                            }

    def get_dependecies_in_code(self, source_code):
        tree = parser.parse(bytes(source_code, "utf-8"))
        captures = self.dep_query.captures(tree.root_node)
        deps = set()

        for node, _ in captures:
            deps.add(source_code[node.start_byte:node.end_byte])
        return deps

    def get_context(self, target_func_name):
        if target_func_name not in self.symbol_map:
            possible_matches = [k for k in self.symbol_map.keys() if k.endswith(f"::{target_func_name}")]
            if not possible_matches:
                return f"Error: Not found '{target_func_name}'"
            target_func_name = possible_matches[0]

        visited = set()
        queue = [target_func_name]
        final_output = []

        ignore_list = {'int', 'float', 'double', 'bool', 'void', 'std', 'vector', 'string', 'cout', 'endl', 'return', 'if',
                  'else', 'for', 'while', 'true', 'false', 'auto', 'const'}
        while queue:
            current_name = queue.pop(0)
            if current_name in visited or current_name in ignore_list:
                continue
            visited.add(current_name)

            if current_name in self.symbol_map:
                info = self.symbol_map[current_name]

                type_label = "UNKNOWN"
                if info['type'] == 'function_definition':
                    type_label = "FUNCTION"
                elif info['type'] == 'class_specifier':
                    type_label = "CLASS"
                elif info['type'] == 'struct_specifier':
                    type_label = "STRUCT"
                elif info['type'] == 'preproc_def':
                    type_label = "MACRO/CONSTANT"
                elif info['type'] == 'declaration':
                    type_label = "GLOBAL VARIABLE"
                elif info['type'] == 'preproc_include':
                    type_label = "LIBRARY"

                final_output.append(f"// --- {type_label}: {current_name} (File: {info['file']}) ---")
                final_output.append(info['code'])
                final_output.append("")

                deps = self.get_dependecies_in_code(info['code'])
                for d in deps:
                    if d not in visited and d not in ignore_list:
                        queue.append(d)
                    else:
                        for k in self.symbol_map:
                            if k.endswith(f"::{d}"):
                                queue.append(k)
                                break
        return "\n".join(final_output)



# def test_file(str):
#     with open(str, "rb") as f:
#         code = f.read()
#
#     tree = parser.parse(code)
#     result = print_tree(tree.root_node, code)
#     return (result)
#
# def print_tree(node, code, indent=0) -> str:
#     res = ""
#     res += "  " * indent + f"{node.type} [{node.start_point} - {node.end_point}]\n"
#     for child in node.children:
#         res += print_tree(child, code, indent + 1)
#     return res


with open("Button_cpp.txt", "w", encoding="utf-8") as f:
    # code = (test_file("D:\Lab\Multi_Agents\Flappy-Bird-Qt\source\common.h"))
    extractor = CppCodeExtractor(r"D:\Lab\Multi_Agents\Flappy-Bird-Qt")
    extractor.index_project()
    f.write(extractor.get_context("ButtonFuncs::play"))