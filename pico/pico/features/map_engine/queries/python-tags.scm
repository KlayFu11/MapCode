; MapCode Python tags query.
; Adapted from Aider's python tree-sitter tags query.
; Source project: Aider, licensed under Apache License 2.0.
; Local modifications: this MapCode-owned copy is scoped to v1 Python
; definition/reference capture names used by MapEngine.

(module
  (assignment
    left: (identifier) @name.definition.constant) @definition.constant)

(class_definition
  name: (identifier) @name.definition.class) @definition.class

(function_definition
  name: (identifier) @name.definition.function) @definition.function

(call
  function: [
    (identifier) @name.reference.call
    (attribute
      attribute: (identifier) @name.reference.call)
  ]) @reference.call
