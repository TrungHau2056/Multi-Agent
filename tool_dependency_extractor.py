from mimetypes import knownfiles

from tree_sitter import Language, Parser
from langchain.tools import tool
import os, json

Language.build_library(
    'build/my-languages.so',
    ['tree-sitter-cpp']
)

CPP_LANGUAGE = Language('build/my-languages.so','cpp')

parser = Parser()
parser.set_language(CPP_LANGUAGE)

def extract_includes(node, code):
    includes = []
    if node.type == 'preproc_include':
        text = code[node.start_byte:node.end_byte].decode('utf-8')
        includes.append(text)
    for child in node.children:
        includes.extend(extract_includes(child, code))
    return includes

def extract_classes(node, code):
    classes = {}
    if node.type == "class_specifier":
        class_name_node = node.child_by_field_name("name")
        class_body_node = node.child_by_field_name("body")
        if class_name_node:
            class_name = code[class_name_node.start_byte:class_name_node.end_byte].decode('utf-8')
            class_body = code[class_body_node.start_byte:class_body_node.end_byte].decode('utf-8') if class_body_node else ""
            classes[class_name] = class_body
    for child in node.children:
        classes.update(extract_classes(child, code))
    return classes

def extract_functions_and_calls(node, code, all_classes):
    results = []

    if node.type == 'function_definition':
        declarator = node.child_by_field_name("declarator")
        func_name = None

        # 🔍 Lấy tên hàm chính xác
        if declarator:
            # duyệt sâu để tìm identifier hoặc qualified_identifier
            for child in declarator.children:
                if child.type in ("identifier", "qualified_identifier"):
                    func_name = code[child.start_byte:child.end_byte].decode('utf-8').strip()
                    break

        if not func_name:
            func_name = "<anonymous>"

        # 🔍 Lấy danh sách tham số
        params_code = ""
        if declarator:
            for c in declarator.children:
                if c.type == 'parameter_list':
                    params_code = code[c.start_byte:c.end_byte].decode('utf-8').strip()
                    break

        # 🔍 Lấy phần thân hàm
        body_node = node.child_by_field_name("body")
        body_code = ""
        if body_node:
            body_code = code[body_node.start_byte:body_node.end_byte].decode('utf-8').strip()

        # 🔍 Tìm phần khởi tạo constructor (nếu có)
        def find_constructor_initializer(node):
            if node.type in ("constructor_initializer", "field_initializer_list", "initializer_list"):
                return code[node.start_byte:node.end_byte].decode('utf-8').strip()
            for child in node.children:
                result = find_constructor_initializer(child)
                if result:
                    return result
            return ""

        init_code = find_constructor_initializer(node)
        full_body = init_code + "\n" + body_code if init_code else body_code

        # 🔍 Tìm các hàm được gọi trong thân hàm
        calls = []
        def find_calls(n):
            if n.type == 'call_expression':
                func_node = n.child_by_field_name("function")
                if func_node:
                    name = code[func_node.start_byte:func_node.end_byte].decode('utf-8').strip()
                    calls.append(name)
            for c in n.children:
                find_calls(c)

        if body_node:
            find_calls(body_node)

        # 🔍 Tìm các class có thể được dùng trong body
        object_deps = find_object_dependencies(body_node, code, all_classes.keys()) if body_node else set()

        results.append({
            "function_name": func_name,
            "params": params_code,
            "body": full_body,
            "calls": calls,
            "object_dependencies": {cls: all_classes[cls] for cls in object_deps}
        })

    # Duyệt đệ quy toàn bộ cây
    for child in node.children:
        results.extend(extract_functions_and_calls(child, code, all_classes))
    return results


def analyze_file(path):
    try:
        with open(path, "rb") as f:
            code = f.read()
        tree = parser.parse(code)
        root = tree.root_node

        includes = extract_includes(root, code)
        all_classes = extract_classes(root, code)
        functions = extract_functions_and_calls(root, code, all_classes)

        if not functions:
            print(f"{path} has no functions")
        else:
            for func in functions:
                print(f"{path} -> Found function: {func['function_name']}")

        return {
            'includes': includes,
            'functions': functions,
            'classes': all_classes
        }

    except Exception as e:
        return {'error': str(e)}

def find_object_dependencies(node, code, known_classes):
    deps = set()
    if node.type in ("call_expression", "type_identifier", "constructor_initializer"):
        name = code[node.start_byte:node.end_byte].decode('utf-8').strip()
        if name in known_classes:
            deps.add(name)
    for child in node.children:
        deps.update(find_object_dependencies(child, code, known_classes))
    return deps


# @tool("analysis_project", return_direct=True)
def analysis_project(filepath: str, focal_method: str):
    """
    Phân tích mã cũ pháp C++ và trả về AST dạng text
    """
    project_data = {}
    for root, _, files in os.walk(filepath):
        for file in files:
            if file.endswith(('.cpp', '.h')):
                path = os.path.join(root, file)
                project_data[path] = analyze_file(path)

    all_functions = {}

    for path, file_data in project_data.items():
        if 'functions' not in file_data:
            print(f"{path} has no functions")
            continue
        for func in file_data['functions']:
            all_functions[func['function_name']] = func

    def find_best_match(call_name, all_functions):
        # Nếu call có dạng A::B thì ưu tiên khớp chính xác
        if call_name in all_functions:
            return call_name

        # Nếu không, tìm function_name chứa ở cuối
        for name in all_functions:
            # ví dụ: call_name="setColor", function_name="Bird::setColor(int)"
            if name.endswith(call_name) or name.split('(')[0].endswith(call_name):
                return name

        # Nếu vẫn không có, thử loại bỏ phần pointer -> call
        if "->" in call_name:
            call_name = call_name.split("->")[-1]
            return find_best_match(call_name, all_functions)

        # Không khớp được
        return None

    def build_dependencies_tree(func_name, all_functions, visited = None):
        if visited is None:
            visited = set()

        if find_best_match(func_name, all_functions) == None:
            all_functions[func_name] = {
                'function_name': func_name,
                'params': "",
                'body': "",
                'calls': [],
            }

        if func_name in visited:
            return None
        visited.add(func_name)

        func_data = all_functions[func_name]

        if not func_data:
            return None

        dept_dict = {
            "function_name": func_data["function_name"],
            "params": func_data["params"],
            "body": func_data["body"],
            "calls": [],
        }

        for call_name in func_data["calls"]:
            matched = find_best_match(call_name, all_functions)
            if matched:
                child_dep = build_dependencies_tree(matched, all_functions, visited)
                if child_dep:
                    dept_dict["calls"].append(child_dep)

        return dept_dict

    dependency_tree = build_dependencies_tree(focal_method, all_functions)
    return dependency_tree


#
# base_dir = "Flappy-Bird-Qt"
# focal_method = """Bird::Bird(const QPointF& pos, const QPixmap& pixmap, const qreal &groundStartPosY, int scrWidth, int scrHeight, qreal scaleF)"""
# data = analysis_project(base_dir, focal_method)
# with open("project_analysis.json", "w") as f:
#     json.dump(data, f, ensure_ascii=False, indent=2)

def test_file(str):
    with open(str, "rb") as f:
        code = f.read()

    tree = parser.parse(code)
    result = print_tree(tree.root_node, code)
    return (result)

def print_tree(node, code, indent=0) -> str:
    res = ""
    res += "  " * indent + f"{node.type} [{node.start_point} - {node.end_point}]\n"
    for child in node.children:
        res += print_tree(child, code, indent + 1)
    return res


with open("common.txt", "w") as f:
    code = (test_file("D:\Lab\Multi_Agents\Flappy-Bird-Qt\source\common.h"))
    f.write(code)


