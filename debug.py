from tree_sitter import Language, Parser

# build lại nếu chưa có
Language.build_library(
    'build/my-languages.so',
    ['tree-sitter-cpp']
)
CPP_LANGUAGE = Language('build/my-languages.so', 'cpp')

parser = Parser()
parser.set_language(CPP_LANGUAGE)

file_path = "Flappy-Bird-Qt/source/Bird/Bird.cpp"  # <-- sửa nếu khác
with open(file_path, "rb") as f:
    code = f.read()

tree = parser.parse(code)
root = tree.root_node

def print_node(node, code, level=0):
    indent = "  " * level
    print(f"{indent}{node.type}")
    for child in node.children:
        print_node(child, code, level + 1)

print_node(root, code)
