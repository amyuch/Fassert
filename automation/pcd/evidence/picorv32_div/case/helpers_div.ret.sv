/// Helper Assertion Begin
	wire h_is_divu = (wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011) &&
	                 (wrapper.uut.dbg_insn_opcode[14:12] == 3'b100) &&
	                 (wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001);
	wire h_rvfi_divu = (rvfi_insn[6:0] == 7'b0110011) &&
	                   (rvfi_insn[14:12] == 3'b100) &&
	                   (rvfi_insn[31:25] == 7'b0000001);

	reg        h_wb_seen;
	reg [31:0] h_wb_opcode;
	reg [4:0]  h_wb_rd;
	reg [31:0] h_wb_wdata;
	reg [31:0] h_wb_rs1;
	reg [31:0] h_wb_rs2;

	always @(posedge clock) begin
		if (reset) begin
			h_wb_seen   <= 1'b0;
			h_wb_opcode <= 32'd0;
			h_wb_rd     <= 5'd0;
			h_wb_wdata  <= 32'd0;
			h_wb_rs1    <= 32'd0;
			h_wb_rs2    <= 32'd0;
		end else begin
			if (rvfi_valid)
				h_wb_seen <= 1'b0;
			if (wrapper.uut.cpuregs_write && h_is_divu) begin
				h_wb_seen   <= 1'b1;
				h_wb_opcode <= wrapper.uut.dbg_insn_opcode;
				h_wb_rd     <= wrapper.uut.latched_rd;
				h_wb_wdata  <= wrapper.uut.cpuregs_wrdata;
				h_wb_rs1    <= wrapper.uut.reg_op1;
				h_wb_rs2    <= wrapper.uut.reg_op2;
			end
		end
	end

	// Divider control/data-path observation (unsigned quotient).
	wire p_div_start_i = wrapper.uut.genblk2.pcpi_div.start &&
	                     wrapper.uut.genblk2.pcpi_div.instr_div;
	reg  p_div_active;
	reg [31:0] p_div_m;
	reg [31:0] p_div_n;
	reg [5:0]  p_div_k;
	wire p_div_loop = wrapper.uut.genblk2.pcpi_div.running &&
	                  (wrapper.uut.genblk2.pcpi_div.quotient_msk != 0) && p_div_active;

	always @(posedge clock) begin
		if (reset) begin
			p_div_m <= 32'd0;
			p_div_n <= 32'd0;
			p_div_k <= 6'd0;
			p_div_active <= 1'b0;
		end else if (p_div_start_i) begin
			p_div_m <= wrapper.uut.pcpi_rs1[31] ? -wrapper.uut.pcpi_rs1 : wrapper.uut.pcpi_rs1;
			p_div_n <= wrapper.uut.pcpi_rs2[31] ? -wrapper.uut.pcpi_rs2 : wrapper.uut.pcpi_rs2;
			p_div_k <= 6'd31;
			p_div_active <= 1'b1;
		end else begin
			if (p_div_loop) p_div_k <= p_div_k - 6'd1;
			if (!wrapper.uut.genblk2.pcpi_div.running ||
			    !wrapper.uut.genblk2.pcpi_div.instr_div)
				p_div_active <= 1'b0;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			h_rvfi_insn_eq: assert (rvfi_insn == $past(wrapper.uut.dbg_insn_opcode));
			h_rvfi_pc_rdata_eq: assert (rvfi_pc_rdata == $past(wrapper.uut.dbg_insn_addr));
			h_rvfi_valid_eq: assert (rvfi_valid == $past((!reset) && (wrapper.uut.launch_next_insn || wrapper.uut.trap) && wrapper.uut.dbg_valid_insn));
			h_rvfi_rs1_eq: assert (!(rvfi_valid && check && h_rvfi_divu) || rvfi_rs1_rdata == $past(wrapper.uut.dbg_rs1val_valid ? wrapper.uut.dbg_rs1val : 32'd0));
			h_rvfi_rs2_eq: assert (!(rvfi_valid && check && h_rvfi_divu) || rvfi_rs2_rdata == $past(wrapper.uut.dbg_rs2val_valid ? wrapper.uut.dbg_rs2val : 32'd0));
			h_rvfi_rd_eq: assert (!(rvfi_valid && check && h_rvfi_divu) || rvfi_rd_wdata ==
				($past(reset) ? 32'd0 :
				 ($past(wrapper.uut.cpuregs_write) && !$past(wrapper.uut.irq_state)) ?
					($past(wrapper.uut.latched_rd) ? $past(wrapper.uut.cpuregs_wrdata) : 32'd0) :
				 ($past(rvfi_valid) ? 32'd0 : $past(rvfi_rd_wdata))));
			h_rvfi_rd_addr_eq: assert (!(rvfi_valid && check && h_rvfi_divu) || rvfi_rd_addr ==
				($past(reset) ? 5'd0 :
				 ($past(wrapper.uut.cpuregs_write) && !$past(wrapper.uut.irq_state)) ?
					$past(wrapper.uut.latched_rd) :
				 ($past(rvfi_valid) ? 5'd0 : $past(rvfi_rd_addr))));

			h_no_irq_on_divu: assert (!(rvfi_valid && check && h_rvfi_divu) || !wrapper.uut.dbg_irq_call);
			h_no_trap_on_divu: assert (!(rvfi_valid && check && h_rvfi_divu) || !wrapper.uut.trap);

			h_commit_rd: assert (!(wrapper.uut.cpuregs_write && h_is_divu) ||
				wrapper.uut.latched_rd == wrapper.uut.dbg_insn_opcode[11:7]);
			h_commit_rs1: assert (!(wrapper.uut.cpuregs_write && h_is_divu && wrapper.uut.dbg_rs1val_valid) ||
				wrapper.uut.dbg_rs1val == wrapper.uut.reg_op1);
			h_commit_rs2: assert (!(wrapper.uut.cpuregs_write && h_is_divu && wrapper.uut.dbg_rs2val_valid) ||
				wrapper.uut.dbg_rs2val == wrapper.uut.reg_op2);

			h_launch_opcode: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_divu) ||
				wrapper.uut.cpuregs_write ||
				(h_wb_seen && wrapper.uut.dbg_insn_opcode == h_wb_opcode));
			h_launch_operands: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_divu) ||
				(wrapper.uut.cpuregs_write ?
					(wrapper.uut.dbg_rs1val_valid && wrapper.uut.dbg_rs2val_valid &&
					 wrapper.uut.dbg_rs1val == wrapper.uut.reg_op1 &&
					 wrapper.uut.dbg_rs2val == wrapper.uut.reg_op2) :
					(h_wb_seen && wrapper.uut.dbg_rs1val_valid && wrapper.uut.dbg_rs2val_valid &&
					 wrapper.uut.dbg_rs1val == h_wb_rs1 && wrapper.uut.dbg_rs2val == h_wb_rs2)));
			h_launch_rd_wdata: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_divu) ||
				wrapper.uut.cpuregs_write ||
				(h_wb_seen && rvfi_rd_wdata == (h_wb_rd ? h_wb_wdata : 32'd0)));
			h_launch_rd_eq: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_divu) ||
				wrapper.uut.latched_rd == wrapper.uut.dbg_insn_opcode[11:7]);
			h_launch_rs1_zero: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_divu) ||
				wrapper.uut.dbg_insn_opcode[19:15] != 5'd0 || wrapper.uut.dbg_rs1val == 32'd0);
			h_launch_rs2_zero: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_divu) ||
				wrapper.uut.dbg_insn_opcode[24:20] != 5'd0 || wrapper.uut.dbg_rs2val == 32'd0);

			h_wb_matches_retire: assert (!(rvfi_valid && check && h_rvfi_divu) ||
				(h_wb_seen &&
				 h_wb_rd == rvfi_insn[11:7] &&
				 rvfi_rd_wdata == (h_wb_rd ? h_wb_wdata : 32'd0) &&
				 rvfi_rs1_rdata == h_wb_rs1 &&
				 rvfi_rs2_rdata == h_wb_rs2));

			h_pc_next: assert (!(rvfi_valid && check && h_rvfi_divu) ||
				wrapper.uut.dbg_insn_addr == rvfi_pc_rdata + 32'd4);

		end
	end
/// Helper Assertion End

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
		(rvfi_insn[14:12] == 3'b100) &&
		(rvfi_insn[6:0] == 7'b0110011);
	wire p_rem_retire = rvfi_valid && p_rem_rvfi_rem;
	wire p_rem_wb_sel = wrapper.uut.cpuregs_write && p_rem_is_rem;
	wire p_rem_done = wrapper.uut.genblk2.pcpi_div.running && p_rem_active &&
		(wrapper.uut.genblk2.pcpi_div.quotient_msk == 32'd0) &&
		wrapper.uut.genblk2.pcpi_div.instr_div;

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
				p_rem_m <= wrapper.uut.pcpi_rs1[31] ? -wrapper.uut.pcpi_rs1 : wrapper.uut.pcpi_rs1;
				p_rem_n <= wrapper.uut.pcpi_rs2[31] ? -wrapper.uut.pcpi_rs2 : wrapper.uut.pcpi_rs2;
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
				    !wrapper.uut.genblk2.pcpi_div.instr_div)
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

	// Link-compatible retirement bridge.  The finish-word logic is copied
	// verbatim from the corrected link model, while the h_* history below is
	// the independently checked retirement history.  These are obligations.
	always @(posedge clock) begin
		if (!reset) begin
			if (p_rem_wb_sel)
				p_rem_wb_word_a: assert(wrapper.uut.cpuregs_wrdata == p_rem_finish_word);
			if (p_rem_finish_valid)
				p_rem_finish_word_a: assert(p_rem_finish_word ==
					(p_rem_finish_outsign ? -p_rem_finish_dividend : p_rem_finish_dividend));
			if (checker_inst.spec_valid)
				p_rem_ret_finish_a: assert(p_rem_finish_valid);
			p_rem_seen_not_done_a: assert(!h_wb_seen || !p_rem_done);
			p_rem_seen_word_a: assert(!h_wb_seen || h_wb_wdata == p_rem_finish_word);
			p_rem_wb_done_same_a: assert(!(p_rem_wb_sel && p_rem_done) ||
				p_rem_finish_word == (wrapper.uut.genblk2.pcpi_div.outsign
					? -wrapper.uut.genblk2.pcpi_div.quotient
					:  wrapper.uut.genblk2.pcpi_div.quotient));
			if (checker_inst.spec_valid)
				p_rem_ret_word_a: assert(rvfi_rd_wdata ==
					(rvfi_rd_addr != 5'd0 ? p_rem_finish_word : 32'd0));
		end
	end
