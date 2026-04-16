// without let = constant variable, 
// let = variable that can be reassigned, 
// var = variable that can be reassigned and has function scope

let a = "5"; // a is a string. 
let b = 5;

console.log(a == b); // true, because == does type coercion
console.log(a === b); // false, because === does not do type coercion

// type coercion is when JavaScript automatically converts a value from one type to another.

// for example, when you use the + operator with a string and a number, JavaScript will convert the number to a string and concatenate them.

let c = a + b; // c is "55", because a is a string and b is a number, so JavaScript converts b to a string and concatenates them.