/** Browser globals expected by chat-app.js (classic script). */
import { marked } from "marked";
import DOMPurify from "dompurify";
import vegaEmbed from "vega-embed";

window.marked = marked;
window.DOMPurify = DOMPurify;
window.vegaEmbed = vegaEmbed;
