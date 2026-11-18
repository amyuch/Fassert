// PCD case-local helper assertions for the REM control/data path.
//
// These are obligations, not assumptions: the proof graph must discharge every
// named assertion before it may use the corresponding guarantee.  The names are
// deliberately local to this case and are never imported from another tree.

	wire p_rem_is_rem =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b111) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);

	wire p_rem_start = wrapper.uut.genblk2.pcpi_div.start;
	wire p_rem_start_i = p_rem_start && wrapper.uut.genblk2.pcpi_div.instr_remu;
	reg  p_rem_active;

	reg [31:0] p_rem_m;
	reg [31:0] p_rem_n;
	reg [5:0]  p_rem_k;

	wire p_rem_loop = wrapper.uut.genblk2.pcpi_div.running &&
	                  (wrapper.uut.genblk2.pcpi_div.quotient_msk != 0) && p_rem_active;

	always @(posedge clock) begin
		if (reset) begin
			p_rem_m <= 32'd0;
			p_rem_n <= 32'd0;
			p_rem_k <= 6'd0;
			p_rem_active <= 1'b0;
		end else if (p_rem_start_i) begin
			p_rem_m <= (wrapper.uut.genblk2.pcpi_div.instr_div ||
			            wrapper.uut.genblk2.pcpi_div.instr_rem) && wrapper.uut.pcpi_rs1[31]
			           ? -wrapper.uut.pcpi_rs1 : wrapper.uut.pcpi_rs1;
			p_rem_n <= (wrapper.uut.genblk2.pcpi_div.instr_div ||
			            wrapper.uut.genblk2.pcpi_div.instr_rem) && wrapper.uut.pcpi_rs2[31]
			           ? -wrapper.uut.pcpi_rs2 : wrapper.uut.pcpi_rs2;
			p_rem_k <= 6'd31;
			p_rem_active <= 1'b1;
		end else begin
			if (p_rem_loop) p_rem_k <= p_rem_k - 6'd1;
			if (!wrapper.uut.genblk2.pcpi_div.running ||
			    !wrapper.uut.genblk2.pcpi_div.instr_remu)
				p_rem_active <= 1'b0;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// The divider starts with the magnitude operands, zero quotient,
			// the top mask bit, and the scaled divisor.
			if ($past(!reset) && $past(p_rem_start_i)) begin
				p_rem_start_d: assert(wrapper.uut.genblk2.pcpi_div.dividend == p_rem_m);
				p_rem_start_msk: assert(wrapper.uut.genblk2.pcpi_div.quotient_msk == (32'd1 << 31));
				p_rem_start_divisor: assert(wrapper.uut.genblk2.pcpi_div.divisor == (p_rem_n << 31));
				p_rem_start_sign: assert(wrapper.uut.genblk2.pcpi_div.outsign == 1'b0);
			end

			// Loop scaling: at step k the divisor is N<<k and the mask is 1<<k.
			if (p_rem_loop) begin
				p_rem_div_k: assert(wrapper.uut.genblk2.pcpi_div.divisor == (p_rem_n << p_rem_k));
				p_rem_msk_k: assert(wrapper.uut.genblk2.pcpi_div.quotient_msk == (32'd1 << p_rem_k));
			end

			// One restoring-division step, plus the fixed shift of the mask.
			if ($past(!reset) && $past(p_rem_loop) && !$past(p_rem_start)) begin
				p_rem_step_d: assert(wrapper.uut.genblk2.pcpi_div.dividend ==
					(($past(wrapper.uut.genblk2.pcpi_div.divisor) <= $past(wrapper.uut.genblk2.pcpi_div.dividend))
					 ? $past(wrapper.uut.genblk2.pcpi_div.dividend) - $past(wrapper.uut.genblk2.pcpi_div.divisor)
					 : $past(wrapper.uut.genblk2.pcpi_div.dividend)));
				p_rem_step_msk: assert(wrapper.uut.genblk2.pcpi_div.quotient_msk ==
					($past(wrapper.uut.genblk2.pcpi_div.quotient_msk) >> 1));
			end

			// Data-path observation links.
			if (wrapper.uut.pcpi_div_ready && !wrapper.uut.pcpi_mul_ready)
				p_rem_mux: assert(wrapper.uut.pcpi_int_rd == wrapper.uut.pcpi_div_rd);

			if ($past(!reset) && $past(wrapper.uut.cpu_state == 8'b00100000 &&
			    wrapper.uut.instr_trap && wrapper.uut.pcpi_div_ready))
				p_rem_capture: assert(wrapper.uut.reg_out == $past(wrapper.uut.pcpi_int_rd));

			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store &&
			    !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)
				p_rem_wb: assert(wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_out);

			if ($past(!reset) && $past(wrapper.uut.cpuregs_write) &&
			    !$past(wrapper.uut.irq_state) && $past(p_rem_is_rem))
				p_rem_rvfi_wdata: assert(wrapper.uut.rvfi_rd_wdata ==
					($past(wrapper.uut.latched_rd) ? $past(wrapper.uut.cpuregs_wrdata) : 32'd0));

			if (checker_inst.spec_valid)
				p_rem_rvfi_rd: assert(rvfi_rd_addr == rvfi_insn[11:7]);

			// The divider owns the result at the REM finish edge.
			if ($past(!reset) && wrapper.uut.pcpi_div_ready &&
			    p_rem_active && $past(wrapper.uut.genblk2.pcpi_div.instr_remu))
				p_rem_finish: assert(wrapper.uut.pcpi_div_rd ==
					($past(wrapper.uut.genblk2.pcpi_div.outsign)
					 ? -$past(wrapper.uut.genblk2.pcpi_div.dividend)
					 :  $past(wrapper.uut.genblk2.pcpi_div.dividend)));
		end
	end

	// ---- retirement / writeback link helpers --------------------------------
	// These mirror the MUL proof's seen/writeback-word control facts.  The
	// divider result is snapshotted at the divider finish event itself, so the
	// snapshot is established by construction rather than by trusting an
	// arbitrary ready state.
	wire p_rem_rvfi_rem =
		(rvfi_insn[31:25] == 7'b0000001) &&
		(rvfi_insn[14:12] == 3'b111) &&
		(rvfi_insn[6:0] == 7'b0110011);
	wire p_rem_retire = rvfi_valid && p_rem_rvfi_rem;
	wire p_rem_wb_sel = wrapper.uut.cpuregs_write && p_rem_is_rem;
	wire p_rem_done = wrapper.uut.genblk2.pcpi_div.running && p_rem_active &&
		(wrapper.uut.genblk2.pcpi_div.quotient_msk == 32'd0) &&
		wrapper.uut.genblk2.pcpi_div.instr_remu;

	reg [31:0] p_rem_start_rs1;
	reg [31:0] p_rem_start_rs2;
	reg [31:0] p_rem_finish_word;
	reg [31:0] p_rem_finish_dividend;
	reg [31:0] p_rem_finish_m;
	reg [31:0] p_rem_finish_n;
	reg        p_rem_finish_outsign;
	reg        p_rem_pcpi_valid_q;
	reg        p_rem_finish_valid;

	always @(posedge clock) begin
		if (reset) begin
			p_rem_start_rs1 <= 32'd0;
			p_rem_start_rs2 <= 32'd0;
			p_rem_finish_word <= 32'd0;
			p_rem_finish_dividend <= 32'd0;
			p_rem_finish_m <= 32'd0;
			p_rem_finish_n <= 32'd0;
			p_rem_finish_outsign <= 1'b0;
			p_rem_finish_valid <= 1'b0;
			p_rem_pcpi_valid_q <= 1'b0;
		end else begin
			if (p_rem_start_i) begin
				p_rem_start_rs1 <= wrapper.uut.pcpi_rs1;
				p_rem_start_rs2 <= wrapper.uut.pcpi_rs2;
			end
			if (p_rem_done) begin
				p_rem_finish_word <= wrapper.uut.genblk2.pcpi_div.outsign
					? -wrapper.uut.genblk2.pcpi_div.dividend
					:  wrapper.uut.genblk2.pcpi_div.dividend;
				p_rem_finish_dividend <= wrapper.uut.genblk2.pcpi_div.dividend;
				p_rem_finish_m <= p_rem_m;
				p_rem_finish_n <= p_rem_n;
				p_rem_finish_outsign <= wrapper.uut.genblk2.pcpi_div.outsign;
				p_rem_finish_valid <= 1'b1;
			end
			if (rvfi_valid)
				p_rem_finish_valid <= 1'b0;
			p_rem_pcpi_valid_q <= wrapper.uut.pcpi_valid;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin

			// Timeout/counter control lemmas.  These are obligations, not
			// assumptions: the control cill run must discharge every one.

			if (p_rem_wb_sel) begin
				p_rem_wb_finish_a: assert(p_rem_finish_valid);
				p_rem_wb_word_a: assert(wrapper.uut.cpuregs_wrdata == p_rem_finish_word);
			end
			if (checker_inst.spec_valid) begin
				p_rem_ret_finish_a: assert(p_rem_finish_valid);
			end
			if (p_rem_finish_valid) begin
				p_rem_finish_word_a: assert(p_rem_finish_word ==
					(p_rem_finish_outsign ? -p_rem_finish_dividend : p_rem_finish_dividend));
				p_rem_finish_sign_a: assert(p_rem_finish_outsign == 1'b0);
			end
		end
	end

// Writeback-result capture.  p_rem_wb_word_a says the writeback data is the
// finish word; this register carries that value to the retirement edge so the
// RVFI result check is a state invariant instead of a cross-cycle guess.
reg [31:0] p_rem_wb_value;
reg        p_rem_wb_value_valid;
always @(posedge clock) begin
	if (reset) begin
		p_rem_wb_value <= 32'd0;
		p_rem_wb_value_valid <= 1'b0;
	end else begin
		if (p_rem_wb_sel)
			p_rem_wb_value <= p_rem_finish_word;
		if (rvfi_valid)
			p_rem_wb_value_valid <= 1'b0;
		else if (p_rem_wb_sel)
			p_rem_wb_value_valid <= 1'b1;
	end
end
always @(posedge clock) begin
	if (!reset) begin
		// While the captured writeback result is valid it is the finish word;
		// a following divide may already be running, so the guard is required
		// for the induction (the retirement itself is still the finish cycle).
		p_rem_wb_inv_a: assert(!p_rem_wb_value_valid ||
			p_rem_wb_value == p_rem_finish_word);
	end
end
always @(posedge clock) begin
	if (!reset) begin
		if (checker_inst.spec_valid)
			p_rem_ret_wb_valid_a: assert(p_rem_wb_value_valid);
		if (p_rem_wb_value_valid)
			p_rem_ret_wb_ga: assert(rvfi_rd_wdata ==
				(rvfi_rd_addr != 5'd0 ? p_rem_wb_value : 32'd0));
	end
end
