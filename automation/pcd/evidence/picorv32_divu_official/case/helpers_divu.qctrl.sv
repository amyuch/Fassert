// PCD case-local helper assertions for the REM control/data path.
//
// These are obligations, not assumptions: the proof graph must discharge every
// named assertion before it may use the corresponding guarantee.  The names are
// deliberately local to this case and are never imported from another tree.

	wire p_rem_is_rem =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b101) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);

	wire p_rem_start = wrapper.uut.genblk2.pcpi_div.start;
	wire p_rem_start_i = p_rem_start && wrapper.uut.genblk2.pcpi_div.instr_divu;
	reg  p_rem_active;

	reg [31:0] p_rem_m;
	reg [31:0] p_rem_n;
	reg [5:0]  p_rem_k;
	reg [63:0] p_rem_prod;
	reg [31:0] p_rem_qsum;

	wire p_rem_loop = wrapper.uut.genblk2.pcpi_div.running &&
	                  (wrapper.uut.genblk2.pcpi_div.quotient_msk != 0) && p_rem_active;
	wire p_rem_arith = wrapper.uut.genblk2.pcpi_div.running && p_rem_active;

	always @(posedge clock) begin
		if (reset) begin
			p_rem_m <= 32'd0;
			p_rem_n <= 32'd0;
			p_rem_k <= 6'd0;
			p_rem_prod <= 64'd0;
			p_rem_qsum <= 32'd0;
			p_rem_active <= 1'b0;
		end else if (p_rem_start_i) begin
			p_rem_m <= ((wrapper.uut.genblk2.pcpi_div.instr_div || wrapper.uut.genblk2.pcpi_div.instr_rem) && wrapper.uut.pcpi_rs1[31]) ? -wrapper.uut.pcpi_rs1 : wrapper.uut.pcpi_rs1;
			p_rem_n <= ((wrapper.uut.genblk2.pcpi_div.instr_div || wrapper.uut.genblk2.pcpi_div.instr_rem) && wrapper.uut.pcpi_rs2[31]) ? -wrapper.uut.pcpi_rs2 : wrapper.uut.pcpi_rs2;
			p_rem_k <= 6'd31;
			p_rem_prod <= 64'd0;
			p_rem_qsum <= 32'd0;
			p_rem_active <= 1'b1;
		end else begin
			if (p_rem_loop) p_rem_k <= p_rem_k - 6'd1;
			if (p_rem_loop && (wrapper.uut.genblk2.pcpi_div.divisor <= {32'd0, wrapper.uut.genblk2.pcpi_div.dividend})) begin
				p_rem_prod <= p_rem_prod + {1'b0, wrapper.uut.genblk2.pcpi_div.divisor};
				p_rem_qsum <= p_rem_qsum + wrapper.uut.genblk2.pcpi_div.quotient_msk;
			end
			if (!wrapper.uut.genblk2.pcpi_div.running ||
			    !wrapper.uut.genblk2.pcpi_div.instr_divu)
				p_rem_active <= 1'b0;
		end
	end

	// Control-only carrier for the qsum arithmetic.  The state update above is
	// byte-for-byte the qsum helper's update; only the five control assertions
	// consumed by the arithmetic proof are exposed here.
	always @(posedge clock) begin
		if (!reset) begin
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
