-- table-widths.lua
-- Redistribuye los anchos de columna de tablas pandoc proporcionalmente
-- al contenido real de cada columna.
--
-- Actúa siempre (tanto si las columnas tienen anchos explícitos como si
-- usan ColWidthDefault), lo que evita el problema habitual de LLMs que
-- generan separadores de igual longitud y producen columnas iguales.

function Table(el)
    local ok, result = pcall(function()
        local spec = el.colspec
        local n = #spec
        if n < 2 then return el end

        -- Medir longitud máxima de texto por columna
        local maxlen = {}
        for i = 1, n do maxlen[i] = 1 end

        local function measure_cells(cells)
            for i, cell in ipairs(cells) do
                if i <= n then
                    local s = pandoc.utils.stringify(cell.contents)
                    local len = utf8.len(s) or #s
                    if len > maxlen[i] then maxlen[i] = len end
                end
            end
        end

        -- Cabecera
        for _, row in ipairs(el.head.rows) do
            measure_cells(row.cells)
        end

        -- Cuerpo
        for _, body in ipairs(el.bodies) do
            for _, row in ipairs(body.body) do
                measure_cells(row.cells)
            end
        end

        -- Calcular total y redistribuir con mínimo del 5% por columna
        local total = 0
        for i = 1, n do total = total + maxlen[i] end
        if total == 0 then return el end

        local min_w = 0.05
        local spare = 1.0 - min_w * n

        for i = 1, n do
            if spare < 0 then
                spec[i][2] = 1.0 / n
            else
                spec[i][2] = min_w + spare * (maxlen[i] / total)
            end
        end

        el.colspec = spec
        return el
    end)

    if ok then return result else return el end
end
