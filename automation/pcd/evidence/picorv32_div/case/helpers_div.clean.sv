// PCD case-local helper assertions for the DIV control/data path.
//
// These are obligations, not assumptions: the clean cill run must discharge
// every named assertion before the arithmetic proof may use it.  This helper
// is intentionally smaller than the retirement carrier; it exposes only the
// divider loop facts consumed by the qsum arithmetic.

	wire p_rem_is_rem =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b100) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);

	wire p_rem_start = wrapper.uut.genblk2.pcpi_div.start;
	wire p_rem_start_i = p_rem_start && wrapper.uut.genblk2.pcpi_div.instr_div;
	reg  p_rem_active;

	reg [31:0] p_rem_m;
	reg [31:0] p_rem_n;
	reg [5:0]  p_rem_k;

	wire p_rem_loop = wrapper.uut.genblk2.pcpi_div.running &&
	                  (wrapper.uut.genblk2.pcpi_div.quotient_msk != 0) && p_rem_active;
	wire p_rem_arith = wrapper.uut.genblk2.pcpi_div.running && p_rem_active;

	always @(posedge clock) begin
		if (reset) begin
			p_rem_m <= 32'd0;
			p_rem_n <= 32'd0;
			p_rem_k <= 6'd0;
			p_rem_active <= 1'b0;
		end else if (p_rem_start_i) begin
			p_rem_m <= wrapper.uut.pcpi_rs1[31] ? -wrapper.uut.pcpi_rs1 : wrapper.uut.pcpi_rs1;
			p_rem_n <= wrapper.uut.pcpi_rs2[31] ? -wrapper.uut.pcpi_rs2 : wrapper.uut.pcpi_rs2;
			p_rem_k <= 6'd31;
			p_rem_active <= 1'b1;
		end else begin
			if (p_rem_loop) p_rem_k <= p_rem_k - 6'd1;
			if (!wrapper.uut.genblk2.pcpi_div.running ||
			    !wrapper.uut.genblk2.pcpi_div.instr_div)
				p_rem_active <= 1'b0;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			if ($past(!reset) && $past(p_rem_start_i)) begin
				p_rem_start_d: assert(wrapper.uut.genblk2.pcpi_div.dividend == p_rem_m);
				p_rem_start_msk: assert(wrapper.uut.genblk2.pcpi_div.quotient_msk == (32'd1 << 31));
				p_rem_start_divisor: assert(wrapper.uut.genblk2.pcpi_div.divisor == (p_rem_n << 31));
				p_rem_start_sign: assert(wrapper.uut.genblk2.pcpi_div.outsign ==
					(($past(wrapper.uut.pcpi_rs1[31]) != $past(wrapper.uut.pcpi_rs2[31])) &&
					 |$past(wrapper.uut.pcpi_rs2)));
			end

			if (p_rem_loop) begin
				p_rem_div_k: assert(wrapper.uut.genblk2.pcpi_div.divisor == (p_rem_n << p_rem_k));
				p_rem_msk_k: assert(wrapper.uut.genblk2.pcpi_div.quotient_msk == (32'd1 << p_rem_k));
			end

			if ($past(!reset) && $past(p_rem_loop) && !$past(p_rem_start)) begin
				p_rem_step_d: assert(wrapper.uut.genblk2.pcpi_div.dividend ==
					(($past(wrapper.uut.genblk2.pcpi_div.divisor) <= $past(wrapper.uut.genblk2.pcpi_div.dividend))
					 ? $past(wrapper.uut.genblk2.pcpi_div.dividend) - $past(wrapper.uut.genblk2.pcpi_div.divisor)
					 : $past(wrapper.uut.genblk2.pcpi_div.dividend)));
				p_rem_step_msk: assert(wrapper.uut.genblk2.pcpi_div.quotient_msk ==
					($past(wrapper.uut.genblk2.pcpi_div.quotient_msk) >> 1));
			end

			if (p_rem_arith)
				p_rem_no_start: assert(!p_rem_start);
		end
	end
