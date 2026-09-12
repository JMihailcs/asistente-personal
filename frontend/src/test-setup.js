import '@testing-library/jest-dom';

// jsdom no implementa scrollIntoView y el chat lo llama en cada render para
// seguir el final de la conversacion. Sin este stub, montar el componente
// explota por una limitacion del entorno, no por un problema del codigo.
Element.prototype.scrollIntoView = () => {};
