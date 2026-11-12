import { createContext, useContext } from "react";

/** true cuando quien mira el reporte es del equipo de Geeks (ve avisos de configuración). */
export const EquipoContext = createContext(false);
export const useEsEquipo = () => useContext(EquipoContext);
