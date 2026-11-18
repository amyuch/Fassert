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


	// ---- retirement / writeback link helpers --------------------------------
	// These mirror the MUL proof's seen/writeback-word control facts.  The
	// divider result is snapshotted at the divider finish event itself, so the
	// snapshot is established by construction rather than by trusting an
	// arbitrary ready state.
	wire p_rem_rvfi_rem =
		(rvfi_insn[31:25] == 7'b0000001) &&
		(rvfi_insn[14:12] == 3'b101) &&
		(rvfi_insn[6:0] == 7'b0110011);
	wire p_rem_retire = rvfi_valid && p_rem_rvfi_rem;
	wire p_rem_wb_sel = wrapper.uut.cpuregs_write && p_rem_is_rem;
	wire p_rem_done = wrapper.uut.genblk2.pcpi_div.running && p_rem_active &&
		(wrapper.uut.genblk2.pcpi_div.quotient_msk == 32'd0) &&
		wrapper.uut.genblk2.pcpi_div.instr_divu;

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
			p_rem_m <= 32'd0;
			p_rem_n <= 32'd0;
			p_rem_k <= 6'd0;
			p_rem_prod <= 64'd0;
			p_rem_qsum <= 32'd0;
			p_rem_active <= 1'b0;
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
				p_rem_m <= wrapper.uut.pcpi_rs1;
				p_rem_n <= wrapper.uut.pcpi_rs2;
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
			if (p_rem_start_i) begin
				p_rem_start_rs1 <= wrapper.uut.pcpi_rs1;
				p_rem_start_rs2 <= wrapper.uut.pcpi_rs2;
			end
			if (p_rem_done) begin
				p_rem_finish_word <= wrapper.uut.genblk2.pcpi_div.outsign
					? -wrapper.uut.genblk2.pcpi_div.quotient
					:  wrapper.uut.genblk2.pcpi_div.quotient;
				p_rem_finish_dividend <= wrapper.uut.genblk2.pcpi_div.quotient;
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


// Operand-consistency snapshots (MUL-style writeback capture).
reg [31:0] p_rem_wb_dbg_rs1;
reg [31:0] p_rem_wb_dbg_rs2;
always @(posedge clock) begin
    if (reset) begin
        p_rem_wb_dbg_rs1 <= 32'd0;
        p_rem_wb_dbg_rs2 <= 32'd0;
    end else if (p_rem_wb_sel) begin
        p_rem_wb_dbg_rs1 <= wrapper.uut.dbg_rs1val_valid ? wrapper.uut.dbg_rs1val : 32'd0;
        p_rem_wb_dbg_rs2 <= wrapper.uut.dbg_rs2val_valid ? wrapper.uut.dbg_rs2val : 32'd0;
    end
end
always @(posedge clock) begin
    if (!reset) begin
        if (p_rem_wb_sel) begin
            p_rem_wb_ops_a_a: assert(p_rem_start_rs1 ==
                (wrapper.uut.dbg_rs1val_valid ? wrapper.uut.dbg_rs1val : 32'd0));
            p_rem_wb_ops_b_a: assert(p_rem_start_rs2 ==
                (wrapper.uut.dbg_rs2val_valid ? wrapper.uut.dbg_rs2val : 32'd0));
        end
        if (p_rem_retire) begin
            p_rem_ret_ops_dbg_a_a: assert(rvfi_rs1_rdata == p_rem_wb_dbg_rs1);
            p_rem_ret_ops_dbg_b_a: assert(rvfi_rs2_rdata == p_rem_wb_dbg_rs2);
        end
        if (checker_inst.spec_valid) begin
            p_rem_ret_ops_rs1_a: assert(p_rem_start_rs1 == (rvfi_insn[19:15] != 5'd0 ? rvfi_rs1_rdata : 32'd0));
            p_rem_ret_ops_rs2_a: assert(p_rem_start_rs2 == (rvfi_insn[24:20] != 5'd0 ? rvfi_rs2_rdata : 32'd0));
        end
    end
end
